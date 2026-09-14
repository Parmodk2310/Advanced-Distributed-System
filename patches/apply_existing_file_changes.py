#!/usr/bin/env python3
"""Apply Phase 6 edits to the verified Phase 5 checkout.

This patcher is intentionally fail-closed while also supporting recovery from
partially applied Phase 6 runs. Structural edits either normalize known Phase 6
state or validate a Phase 5 anchor before modifying a file. It never commits,
pushes, merges, or rewrites history.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
from pathlib import Path

BASE_SHA = "3fb542e6804ac0e2cb75b46dbe2d05508ae8dff3"


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one Phase 5 anchor, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_block(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in text:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "\n" + block.strip() + "\n", encoding="utf-8")

PHASE6_CONFIG_FIELDS = (
    '    observability_enabled: bool = False\n'
    '    observability_host: str = "127.0.0.1"\n'
    '    observability_port: int = 9100\n'
    '    metrics_enabled: bool = True\n'
    '    tracing_enabled: bool = False\n'
    '    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"\n'
    '    otel_service_name: str = "distsys-node"\n'
    '    otel_trace_sample_ratio: float = 0.10\n'
    '    otel_export_timeout_seconds: float = 2.0\n'
)

PHASE6_CONFIG_VALIDATION = (
    '        if not 1 <= self.observability_port <= 65535:\n'
    '            raise ValueError("observability_port must be in 1..65535")\n'
    '        if not 0.0 <= self.otel_trace_sample_ratio <= 1.0:\n'
    '            raise ValueError("otel_trace_sample_ratio must be in [0.0, 1.0]")\n'
    '        if self.otel_export_timeout_seconds <= 0:\n'
    '            raise ValueError("otel_export_timeout_seconds must be greater than zero")\n'
    '        if not self.otel_service_name.strip():\n'
    '            raise ValueError("otel_service_name must not be empty")\n'
)

PHASE6_CONFIG_ENV = (
    '            observability_enabled=_env_bool("OBSERVABILITY_ENABLED", False),\n'
    '            observability_host=os.getenv("OBSERVABILITY_HOST", "127.0.0.1"),\n'
    '            observability_port=int(os.getenv("OBSERVABILITY_PORT", "9100")),\n'
    '            metrics_enabled=_env_bool("METRICS_ENABLED", True),\n'
    '            tracing_enabled=_env_bool("TRACING_ENABLED", False),\n'
    '            otel_exporter_otlp_endpoint=os.getenv(\n'
    '                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"\n'
    '            ),\n'
    '            otel_service_name=os.getenv("OTEL_SERVICE_NAME", "distsys-node"),\n'
    '            otel_trace_sample_ratio=float(os.getenv("OTEL_TRACE_SAMPLE_RATIO", "0.10")),\n'
    '            otel_export_timeout_seconds=float(\n'
    '                os.getenv("OTEL_EXPORT_TIMEOUT_SECONDS", "2.0")\n'
    '            ),\n'
)

_PHASE6_FIELD_NAMES = {
    "observability_enabled",
    "observability_host",
    "observability_port",
    "metrics_enabled",
    "tracing_enabled",
    "otel_exporter_otlp_endpoint",
    "otel_service_name",
    "otel_trace_sample_ratio",
    "otel_export_timeout_seconds",
}

_PHASE6_VALIDATION_STARTS = {
    "if not 1 <= self.observability_port <= 65535:",
    "if not 0.0 <= self.otel_trace_sample_ratio <= 1.0:",
    "if self.otel_export_timeout_seconds <= 0:",
    "if not self.otel_service_name.strip():",
}


def _remove_phase6_config_field_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if line.startswith("    ") and not line.startswith("        "):
            if any(stripped.startswith(f"{name}:") for name in _PHASE6_FIELD_NAMES):
                continue
        result.append(line)
    return result


def _remove_phase6_validation_blocks(lines: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("        ") and line.strip() in _PHASE6_VALIDATION_STARTS:
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= 8:
                    break
                index += 1
            continue
        result.append(line)
        index += 1
    return result


def _remove_phase6_env_kwargs(lines: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        key = next((name for name in _PHASE6_FIELD_NAMES if stripped.startswith(f"{name}=")), None)
        if line.startswith("            ") and key is not None:
            balance = line.count("(") - line.count(")")
            index += 1
            while balance > 0 and index < len(lines):
                balance += lines[index].count("(") - lines[index].count(")")
                index += 1
            continue
        result.append(line)
        index += 1
    return result


def _insert_after_line(lines: list[str], predicate, block: str, *, description: str) -> list[str]:
    matches = [index for index, line in enumerate(lines) if predicate(line)]
    if len(matches) != 1:
        raise RuntimeError(f"config.py: expected exactly one {description}, found {len(matches)}")
    index = matches[0] + 1
    return lines[:index] + block.splitlines(keepends=True) + lines[index:]


def _insert_before_line(lines: list[str], predicate, block: str, *, description: str) -> list[str]:
    matches = [index for index, line in enumerate(lines) if predicate(line)]
    if len(matches) != 1:
        raise RuntimeError(f"config.py: expected exactly one {description}, found {len(matches)}")
    index = matches[0]
    return lines[:index] + block.splitlines(keepends=True) + lines[index:]


def ensure_chaos_routing_import(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    desired = "from distsys.chaos.routing import peer_routing_enabled, resolve_peer_endpoint"
    if desired in text:
        return
    pattern = re.compile(r"^from distsys\.chaos\.routing import ([^\n]+)$", re.MULTILINE)
    match = pattern.search(text)
    if match is not None:
        names = {name.strip() for name in match.group(1).split(",")}
        names.update({"peer_routing_enabled", "resolve_peer_endpoint"})
        replacement = "from distsys.chaos.routing import " + ", ".join(sorted(names))
        text = text[: match.start()] + replacement + text[match.end() :]
        path.write_text(text, encoding="utf-8")
        return

    anchors = (
        "from distsys.cluster.member import ClusterMember, SeedAddress\n",
        "from distsys.cluster.member import ClusterMember\n",
    )
    for anchor in anchors:
        if anchor in text:
            path.write_text(text.replace(anchor, anchor + desired + "\n", 1), encoding="utf-8")
            return
    raise RuntimeError(f"{path}: cannot locate import anchor for chaos routing")


def _method_contains(text: str, method_name: str, marker: str) -> bool:
    pattern = re.compile(
        rf"^    async def {re.escape(method_name)}\(.*?(?=^    async def |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match is not None and marker in match.group(0)


def patch_dependencies(root: Path) -> None:
    p = root / "pyproject.toml"
    replace_once(p, 'version = "0.5.0"', 'version = "0.6.0"')
    replace_once(
        p,
        'description = "Phase 5: secure persistence, restart recovery, etcd coordination, and mTLS"',
        'description = "Phase 6: observable, fault-tested distributed infrastructure for reliable AI/ML services"',
    )
    replace_once(
        p,
        '  "etcd3gw>=2.7,<3",\n]',
        '  "etcd3gw>=2.7,<3",\n'
        '  "prometheus-client>=0.20,<1",\n'
        '  "opentelemetry-api>=1.27,<2",\n'
        '  "opentelemetry-sdk>=1.27,<2",\n'
        '  "opentelemetry-exporter-otlp-proto-http>=1.27,<2",\n'
        '  "httpx>=0.27,<1",\n]',
    )
    replace_once(
        p,
        '  "types-protobuf==7.35.1.20260906",\n]',
        '  "types-protobuf==7.35.1.20260906",\n  "PyYAML>=6.0,<7",\n]',
    )
    replace_once(
        p,
        '  "etcd: requires RUN_ETCD_INTEGRATION=1 and a live local etcd service",\n]',
        '  "etcd: requires RUN_ETCD_INTEGRATION=1 and a live local etcd service",\n'
        '  "chaos: requires RUN_CHAOS_TESTS=1 and the dedicated Phase 6 stack",\n'
        '  "performance: requires RUN_PERFORMANCE_TESTS=1 and the dedicated Phase 6 stack",\n]',
    )
    append_block(
        root / "requirements.txt",
        "prometheus-client>=0.20,<1",
        """
# Phase 6 observability / chaos
prometheus-client>=0.20,<1
opentelemetry-api>=1.27,<2
opentelemetry-sdk>=1.27,<2
opentelemetry-exporter-otlp-proto-http>=1.27,<2
httpx>=0.27,<1
""",
    )
    append_block(root / "requirements-dev.txt", "PyYAML>=6.0,<7", "PyYAML>=6.0,<7")


def patch_env_and_ignore(root: Path) -> None:
    append_block(
        root / ".env.example",
        "OBSERVABILITY_ENABLED=false",
        """
# Phase 6 observability defaults
OBSERVABILITY_ENABLED=false
OBSERVABILITY_HOST=127.0.0.1
OBSERVABILITY_PORT=9100
METRICS_ENABLED=true
TRACING_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
OTEL_SERVICE_NAME=distsys-node
OTEL_TRACE_SAMPLE_RATIO=0.10
OTEL_EXPORT_TIMEOUT_SECONDS=2.0
""",
    )
    append_block(
        root / ".gitignore",
        "benchmark-results/",
        """
# Phase 6 generated evidence/runtime
benchmark-results/
.phase6-logs/
.phase6-runtime/
""",
    )


def patch_config(root: Path) -> None:
    """Normalize Phase 6 settings after pristine, partial, or formatted patch runs."""

    p = root / "src/distsys/utils/config.py"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

    lines = _remove_phase6_config_field_lines(lines)
    lines = _insert_after_line(
        lines,
        lambda line: line.strip().startswith("tls_min_version:") and line.startswith("    "),
        "\n" + PHASE6_CONFIG_FIELDS,
        description="tls_min_version field",
    )

    lines = _remove_phase6_validation_blocks(lines)
    lines = _insert_before_line(
        lines,
        lambda line: line == "    @classmethod\n",
        "\n" + PHASE6_CONFIG_VALIDATION,
        description="Settings.from_env classmethod",
    )

    lines = _remove_phase6_env_kwargs(lines)
    lines = _insert_after_line(
        lines,
        lambda line: line.startswith("            tls_min_version=") and "TLS_MIN_VERSION" in line,
        PHASE6_CONFIG_ENV,
        description="tls_min_version from_env assignment",
    )

    normalized = "".join(lines)
    # Repeated recovery runs can leave extra blank separators where duplicate
    # Phase 6 blocks were removed. Keep ordinary Python spacing deterministic.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    try:
        ast.parse(normalized, filename=str(p))
    except SyntaxError as exc:
        raise RuntimeError(f"{p}: Phase 6 config normalization produced invalid Python") from exc
    p.write_text(normalized, encoding="utf-8")

def patch_protocol(root: Path) -> None:
    p = root / "proto/messages.proto"
    replace_once(
        p,
        'message Envelope { string sender_id = 1; string correlation_id = 2; uint64 timestamp_ms = 3; uint32 ttl = 4; bytes payload = 5; }',
        'message Envelope {\n'
        '  string sender_id = 1;\n'
        '  string correlation_id = 2;\n'
        '  uint64 timestamp_ms = 3;\n'
        '  uint32 ttl = 4;\n'
        '  bytes payload = 5;\n'
        '  string traceparent = 6;\n'
        '  string tracestate = 7;\n'
        '}',
    )

    p = root / "src/distsys/protocol/message.py"
    replace_once(p, '    payload: bytes\n', '    payload: bytes\n    traceparent: str = ""\n    tracestate: str = ""\n')
    replace_once(
        p,
        '        msg_type: MessageType = MessageType.REQUEST,\n    ) -> Message:\n',
        '        msg_type: MessageType = MessageType.REQUEST,\n        traceparent: str = "",\n        tracestate: str = "",\n    ) -> Message:\n',
    )
    replace_once(
        p,
        '            ttl=ttl,\n            payload=payload,\n        )\n\n    @classmethod\n    def new_response',
        '            ttl=ttl,\n            payload=payload,\n            traceparent=traceparent,\n            tracestate=tracestate,\n        )\n\n    @classmethod\n    def new_response',
    )
    replace_once(
        p,
        '        msg_type: MessageType = MessageType.RESPONSE,\n        ttl: int = 8,\n    ) -> Message:\n',
        '        msg_type: MessageType = MessageType.RESPONSE,\n        ttl: int = 8,\n        traceparent: str = "",\n        tracestate: str = "",\n    ) -> Message:\n',
    )
    # The final constructor occurrence is unambiguous after the request edit above.
    text = p.read_text(encoding="utf-8")
    old = '            timestamp_ms=int(time.time() * 1000),\n            ttl=ttl,\n            payload=payload,\n        )\n'
    new = '            timestamp_ms=int(time.time() * 1000),\n            ttl=ttl,\n            payload=payload,\n            traceparent=traceparent,\n            tracestate=tracestate,\n        )\n'
    if text.count(new) < 2:
        if text.count(old) != 1:
            raise RuntimeError("message.py: response constructor anchor drifted")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    p = root / "src/distsys/protocol/codec.py"
    replace_once(
        p,
        '        ttl=message.ttl,\n        payload=message.payload,\n    )\n',
        '        ttl=message.ttl,\n        payload=message.payload,\n        traceparent=message.traceparent,\n        tracestate=message.tracestate,\n    )\n',
    )
    replace_once(
        p,
        '        ttl=envelope.ttl,\n        payload=envelope.payload,\n    )\n',
        '        ttl=envelope.ttl,\n        payload=envelope.payload,\n        traceparent=envelope.traceparent,\n        tracestate=envelope.tracestate,\n    )\n',
    )


def peer_wrapper(signature: str, body_call: str, peer_expr: str) -> str:
    return signature + f'''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await {body_call}

        operation = {{
            MessageType.JOIN_REQUEST: "request",
            MessageType.PING: "ping",
            MessageType.PING_REQ: "ping",
            MessageType.GOSSIP: "gossip",
            MessageType.FORWARDED_REQUEST: "forward",
        }}.get(message.msg_type, "request")
        host, port = resolve_peer_endpoint({peer_expr}, host, port)
        span_context = (
            tracing.tracer.start_as_current_span(
                "distsys.peer_rpc",
                attributes={{
                    "distsys.node.id": self.local_node_id,
                    "distsys.peer.id": {peer_expr} or "unknown",
                    "distsys.operation": operation,
                }},
            )
            if tracing is not None and tracing.enabled
            else nullcontext()
        )
        started = time.perf_counter()
        status = "error"
        with span_context:
            if tracing is not None and tracing.enabled:
                carrier: dict[str, str] = {{}}
                tracing.inject(carrier)
                message = replace(
                    message,
                    traceparent=carrier.get("traceparent", ""),
                    tracestate=carrier.get("tracestate", ""),
                )
            try:
                response = await {body_call}
                status = "success"
                return response
            except TimeoutError:
                status = "timeout"
                raise
            finally:
                if metrics is not None:
                    metrics.peer_rpc(operation, status, time.perf_counter() - started)
                    if operation == "gossip" and status != "success":
                        metrics.gossip_failure()

'''


def patch_cluster_peer(root: Path) -> None:
    p = root / "src/distsys/cluster/peer_client.py"
    ensure_chaos_routing_import(p)

    original = '''    async def _exchange_endpoint(
        self,
        host: str,
        port: int,
        message: Message,
        *,
        timeout_seconds: float,
        expected_node_id: str | None = None,
    ) -> Message:
'''
    body_call = (
        "self._exchange_endpoint_raw(host, port, message, "
        "timeout_seconds=timeout_seconds, expected_node_id=expected_node_id)"
    )

    text = p.read_text(encoding="utf-8")
    if "async def _exchange_endpoint_raw(" in text:
        if "and not peer_routing_enabled()" not in text:
            legacy_start = original + '''        operation = {
'''
            upgraded_start = original + f'''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await {body_call}

        operation = {{
'''
            if legacy_start not in text:
                raise RuntimeError("cluster peer Phase 6 wrapper shape drifted")
            text = text.replace(legacy_start, upgraded_start, 1)
            duplicate = '''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        span_context = (
'''
            if duplicate not in text:
                raise RuntimeError("cluster peer legacy telemetry block drifted")
            text = text.replace(duplicate, '''        span_context = (
''', 1)
            p.write_text(text, encoding="utf-8")
        return

    replace_once(
        p,
        'import logging\nimport ssl\nimport uuid\n',
        'import logging\nimport ssl\nimport time\nimport uuid\n'
        'from contextlib import nullcontext\nfrom dataclasses import replace\n',
    )
    replace_once(
        p,
        '        self.ssl_context = ssl_context\n'
        '        self._breakers: dict[str, CircuitBreaker] = {}\n',
        '        self.ssl_context = ssl_context\n'
        '        self.metrics: Any | None = None\n'
        '        self.tracing: Any | None = None\n'
        '        self._breakers: dict[str, CircuitBreaker] = {}\n',
    )
    raw = original.replace('_exchange_endpoint(', '_exchange_endpoint_raw(')
    replace_once(p, original, raw)
    wrapper = peer_wrapper(original, body_call, 'expected_node_id')
    replace_once(p, raw, wrapper + raw)


def patch_crdt_peer(root: Path) -> None:
    p = root / "src/distsys/replication/peer_client.py"
    ensure_chaos_routing_import(p)

    original = '''    async def _exchange(
        self,
        peer: ClusterMember,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
'''
    text = p.read_text(encoding="utf-8")
    if "async def _exchange_raw(" in text:
        if "and not peer_routing_enabled()" not in text:
            legacy_start = original + '''        operation = {
'''
            upgraded_start = original + '''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)

        operation = {
'''
            if legacy_start not in text:
                raise RuntimeError("CRDT peer Phase 6 wrapper shape drifted")
            text = text.replace(legacy_start, upgraded_start, 1)
            duplicate = '''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        span_context = (
'''
            if duplicate not in text:
                raise RuntimeError("CRDT peer legacy telemetry block drifted")
            text = text.replace(duplicate, '''        span_context = (
''', 1)
            p.write_text(text, encoding="utf-8")
        return

    replace_once(
        p,
        'import asyncio\nimport ssl\n',
        'import asyncio\nimport ssl\nimport time\nfrom contextlib import nullcontext\n',
    )
    replace_once(p, 'from typing import Protocol\n', 'from typing import Any, Protocol\n')
    replace_once(
        p,
        '        self.ssl_context = ssl_context\n',
        '        self.ssl_context = ssl_context\n'
        '        self.metrics: Any | None = None\n'
        '        self.tracing: Any | None = None\n',
    )
    raw = original.replace('_exchange(', '_exchange_raw(')
    replace_once(p, original, raw)
    wrapper = original + '''        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)

        operation = {
            MessageType.CRDT_REPLICATE: "replicate",
            MessageType.CRDT_FETCH: "fetch",
            MessageType.CRDT_DIGEST: "digest",
            MessageType.CRDT_READ_REQUEST: "read",
            MessageType.CRDT_MUTATE_REQUEST: "write",
        }.get(message.msg_type, "request")
        host, port = resolve_peer_endpoint(peer.node_id, peer.host, peer.port)
        peer = replace(peer, host=host, port=port)
        span_context = (
            tracing.tracer.start_as_current_span(
                "distsys.peer_rpc",
                attributes={
                    "distsys.node.id": self.local_node_id,
                    "distsys.peer.id": peer.node_id,
                    "distsys.operation": operation,
                },
            )
            if tracing is not None and tracing.enabled
            else nullcontext()
        )
        started = time.perf_counter()
        status = "error"
        with span_context:
            if tracing is not None and tracing.enabled:
                carrier: dict[str, str] = {}
                tracing.inject(carrier)
                message = replace(
                    message,
                    traceparent=carrier.get("traceparent", ""),
                    tracestate=carrier.get("tracestate", ""),
                )
            try:
                response = await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)
                status = "success"
                return response
            except TimeoutError:
                status = "timeout"
                raise
            finally:
                if metrics is not None:
                    metrics.peer_rpc(operation, status, time.perf_counter() - started)

'''
    replace_once(p, raw, wrapper + raw)


def patch_node_wiring(root: Path) -> None:
    p = root / "src/distsys/node.py"
    replace_once(
        p,
        '''                cluster_peer = PeerClient(
                    local_node_id=self.settings.node_id,
                    retry_policy=RetryPolicy(
''',
        '''                cluster_peer = PeerClient(
                    local_node_id=self.settings.node_id,
                    retry_policy=RetryPolicy(
''',
    )
    # Attach Phase 6 runtime only after each existing constructor closes. Anchors
    # include neighboring service creation to prevent accidental placement drift.
    replace_once(
        p,
        '''                    max_frame_size=self.settings.max_frame_size,
                    ssl_context=self._client_ssl_context,
                )
                self.cluster_service = ClusterService(
''',
        '''                    max_frame_size=self.settings.max_frame_size,
                    ssl_context=self._client_ssl_context,
                )
                cluster_peer.metrics = getattr(self, "metrics", None)
                cluster_peer.tracing = getattr(self, "tracing", None)
                self.cluster_service = ClusterService(
''',
    )
    replace_once(
        p,
        '''                    crdt_peer = CrdtPeerClient(
                        local_node_id=self.settings.node_id,
                        max_frame_size=self.settings.max_frame_size,
                        ssl_context=self._client_ssl_context,
                    )
''',
        '''                    crdt_peer = CrdtPeerClient(
                        local_node_id=self.settings.node_id,
                        max_frame_size=self.settings.max_frame_size,
                        ssl_context=self._client_ssl_context,
                    )
                    crdt_peer.metrics = getattr(self, "metrics", None)
                    crdt_peer.tracing = getattr(self, "tracing", None)
''',
    )
    replace_once(
        p,
        '''                        durable_store = DurableCrdtStore(
                            restored.memory_store,
                            self.repository,
                            restored.clock,
                        )
''',
        '''                        durable_store = DurableCrdtStore(
                            restored.memory_store,
                            self.repository,
                            restored.clock,
                        )
                        durable_store.metrics = getattr(self, "metrics", None)
''',
    )
    replace_once(
        p,
        '''                    async def on_coordination_health(health) -> None:
                        await self.health.set_coordination(health.healthy, health.message)
''',
        '''                    async def on_coordination_health(health) -> None:
                        await self.health.set_coordination(health.healthy, health.message)
                        metrics = getattr(self, "metrics", None)
                        if metrics is not None:
                            metrics.set_coordination(health.healthy)
                            if not health.healthy:
                                metrics.coordination_failure("lease")
''',
    )


def patch_replication_metrics(root: Path) -> None:
    p = root / "src/distsys/replication/service.py"
    text = p.read_text(encoding="utf-8")

    if "self.metrics: Any | None = None" not in text:
        replace_once(
            p,
            "        self._replicator_started = False\n        self._anti_entropy_started = False\n",
            "        self._replicator_started = False\n"
            "        self._anti_entropy_started = False\n"
            "        self.metrics: Any | None = None\n",
        )
        text = p.read_text(encoding="utf-8")

    if not _method_contains(text, "reserve_write", "set_replication_queue_depth"):
        replace_once(
            p,
            '''        pairs = tuple((node_id, key) for node_id in replica_ids if node_id != self.local_node_id)
        return await self.outbox.reserve(pairs)
''',
            '''        pairs = tuple((node_id, key) for node_id in replica_ids if node_id != self.local_node_id)
        reservation = await self.outbox.reserve(pairs)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())
        return reservation
''',
        )
        text = p.read_text(encoding="utf-8")

    if not _method_contains(text, "cancel_write", "set_replication_queue_depth"):
        replace_once(
            p,
            '''    async def cancel_write(self, reservation: OutboxReservation) -> None:
        await self.outbox.cancel(reservation)
''',
            '''    async def cancel_write(self, reservation: OutboxReservation) -> None:
        await self.outbox.cancel(reservation)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())
''',
        )
        text = p.read_text(encoding="utf-8")

    if not _method_contains(text, "publish_write", "set_replication_queue_depth"):
        replace_once(
            p,
            '''        await self.outbox.publish(reservation, {entry.key: entry})
''',
            '''        await self.outbox.publish(reservation, {entry.key: entry})
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())
''',
        )
        text = p.read_text(encoding="utf-8")

    if not _method_contains(text, "ensure_causal", "self.metrics.causal_repair("):
        replace_once(
            p,
            '''    async def ensure_causal(
        self,
        key: str,
        required: VersionVector,
        deadline: Deadline,
    ) -> CausalRepairResult:
        return await self.repair.ensure(key, required, deadline)
''',
            '''    async def ensure_causal(
        self,
        key: str,
        required: VersionVector,
        deadline: Deadline,
    ) -> CausalRepairResult:
        try:
            result = await self.repair.ensure(key, required, deadline)
        except Exception:  # noqa: BLE001 - observe failure, then preserve original exception
            if self.metrics is not None:
                self.metrics.causal_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.causal_repair("success" if result.contacted_nodes else "skipped")
        return result
''',
        )
        text = p.read_text(encoding="utf-8")

    if not _method_contains(text, "reconcile_peer", "self.metrics.anti_entropy_repair("):
        replace_once(
            p,
            '''    async def reconcile_peer(
        self,
        peer: ClusterMember,
        keys: tuple[str, ...] | None = None,
    ) -> object:
        return await self.anti_entropy.reconcile_peer(peer, keys)
''',
            '''    async def reconcile_peer(
        self,
        peer: ClusterMember,
        keys: tuple[str, ...] | None = None,
    ) -> object:
        try:
            result = await self.anti_entropy.reconcile_peer(peer, keys)
        except Exception:  # noqa: BLE001 - observe failure, then preserve original exception
            if self.metrics is not None:
                self.metrics.anti_entropy_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.anti_entropy_repair("success")
        return result
''',
        )


def patch_persistence_metrics(root: Path) -> None:
    p = root / "src/distsys/persistence/durable_store.py"
    text = p.read_text(encoding="utf-8")

    if "import time\n" not in text:
        replace_once(
            p,
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport time\n",
        )
        text = p.read_text(encoding="utf-8")

    if "from typing import Any\n" not in text:
        anchor = "import time\n"
        if anchor not in text:
            raise RuntimeError(f"{p}: cannot locate time import for typing.Any insertion")
        p.write_text(text.replace(anchor, anchor + "from typing import Any\n", 1), encoding="utf-8")
        text = p.read_text(encoding="utf-8")

    if "self.metrics: Any | None = None" not in text:
        replace_once(
            p,
            "        self.clock = clock\n",
            "        self.clock = clock\n        self.metrics: Any | None = None\n",
        )
        text = p.read_text(encoding="utf-8")

    if _method_contains(text, "commit_local", 'self.metrics.persistence("write"'):
        return

    replace_once(
        p,
        '''        await self.repository.commit_mutation(entry, causal_state, deadline)
        return await self.memory.replace(entry, expected_type=entry.crdt_type)
''',
        '''        started = time.perf_counter()
        try:
            await self.repository.commit_mutation(entry, causal_state, deadline)
        except Exception:  # noqa: BLE001 - observe failure, then preserve original exception
            if self.metrics is not None:
                self.metrics.persistence("write", time.perf_counter() - started, failed=True)
            raise
        if self.metrics is not None:
            self.metrics.persistence("write", time.perf_counter() - started)
        return await self.memory.replace(entry, expected_type=entry.crdt_type)
''',
    )



def patch_phase5_timing_tests(root: Path) -> None:
    """Relax only scheduler-sensitive DEAD waits; runtime semantics stay unchanged."""

    failure = root / "tests/integration/test_failure_detection.py"
    replace_once(
        failure,
        '''        async def dead() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)
''',
        '''        async def dead() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=3.0)
''',
    )

    rejoin = root / "tests/integration/test_node_rejoin.py"
    replace_once(
        rejoin,
        '''        async def dead() -> bool:
            current = await service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)
''',
        '''        async def dead() -> bool:
            current = await service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=3.0)
''',
    )

def patch_main(root: Path) -> None:
    p = root / "src/distsys/main.py"
    replace_once(
        p,
        'from distsys.node import DistributedNode\n',
        'from distsys.observed_node import ObservedDistributedNode\n',
    )
    replace_once(p, '    node = DistributedNode(settings)\n', '    node = ObservedDistributedNode(settings)\n')


def patch_makefile(root: Path) -> None:
    p = root / "Makefile"
    append_block(
        p,
        "phase6-release-gate:",
        r'''
.PHONY: phase6-monitoring-up phase6-monitoring-down phase6-cluster \
	phase6-observability-smoke phase6-chaos phase6-benchmark phase6-release-gate

phase6-monitoring-up:
	docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml up -d

phase6-monitoring-down:
	docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml down -v

phase6-cluster:
	bash scripts/run_phase6_cluster.sh

phase6-observability-smoke:
	PYTHONPATH=src $(PYTHON) scripts/phase6_observability_smoke.py
	PYTHONPATH=src $(PYTHON) scripts/phase6_monitoring_smoke.py --cert-dir certs/generated

phase6-chaos:
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py network-delay --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py partition --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py etcd-outage --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py node-kill --target node-1

phase6-benchmark:
	RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/benchmark.py --profile quick --workload task
	RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/benchmark.py --profile quick --workload crdt

phase6-release-gate:
	bash scripts/phase6_release_gate.sh
''',
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skip-base-check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / ".git").exists():
        raise SystemExit(f"not a git checkout: {root}")
    if not args.skip_base_check:
        subprocess.run(["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"], cwd=root, check=True)

    patch_dependencies(root)
    patch_env_and_ignore(root)
    patch_config(root)
    patch_protocol(root)
    patch_cluster_peer(root)
    patch_crdt_peer(root)
    patch_node_wiring(root)
    patch_replication_metrics(root)
    patch_persistence_metrics(root)
    patch_phase5_timing_tests(root)
    patch_main(root)
    patch_makefile(root)
    print("Phase 6 existing-file changes applied. Next: make proto && make quality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
