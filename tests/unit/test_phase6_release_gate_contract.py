from pathlib import Path


def test_release_gate_uses_direct_baseline_before_proxy_chaos() -> None:
    script = Path("scripts/phase6_release_gate.sh").read_text(encoding="utf-8")

    direct_start = script.index("start_cluster direct")
    observability = script.index("phase6_observability_smoke.py")
    monitoring = script.index("phase6_monitoring_smoke.py")
    task_benchmark = script.index("--workload task")
    crdt_benchmark = script.index("--workload crdt")
    baseline_stop = script.index("stop_cluster", crdt_benchmark)
    proxy_start = script.index("start_cluster proxy")
    chaos = script.index("for scenario in")

    assert (
        direct_start
        < observability
        < monitoring
        < task_benchmark
        < crdt_benchmark
        < baseline_stop
        < proxy_start
        < chaos
    )

    assert '--manifest "$CURRENT_LOG_DIR/manifest.json"' in script
    assert "BREAKER_RECOVERY_WAIT_SECONDS" not in script


def test_cluster_runner_exits_after_signal_cleanup() -> None:
    script = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    assert "trap cleanup EXIT" in script
    assert "trap terminate INT TERM" in script

    terminate = script[script.index("terminate() {") :]
    terminate = terminate[: terminate.index("}\n")]

    assert "cleanup" in terminate
    assert "exit 0" in terminate
    assert "while true; do sleep 3600; done" not in script
    assert "RUNNER_IDLE_PID=$!" in script
    assert 'wait "$RUNNER_IDLE_PID"' in script


def test_node_launcher_supports_direct_and_proxy_peer_routing() -> None:
    script = Path("scripts/phase6_start_node.sh").read_text(encoding="utf-8")

    assert 'PHASE6_PEER_ROUTING="${PHASE6_PEER_ROUTING:-direct}"' in script
    assert 'case "$PHASE6_PEER_ROUTING" in' in script
    assert "direct)" in script
    assert "proxy)" in script
    assert "unsupported PHASE6_PEER_ROUTING" in script

    assert "export RUN_CHAOS_TESTS=1 " "PHASE6_PEER_PROXY_MAP=" not in script


def test_phase6_compose_defines_containerized_nodes() -> None:
    import yaml

    compose = yaml.safe_load(
        Path("deploy/monitoring/docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    expected = {
        "node-0": (18000, 9100),
        "node-1": (18001, 9101),
        "node-2": (18002, 9102),
    }

    for node_id, (app_port, obs_port) in expected.items():
        assert node_id in services

        service = services[node_id]

        assert service["build"]["context"] == "../.."
        assert service["build"]["dockerfile"] == "deploy/monitoring/Dockerfile.node"

        assert f"127.0.0.1:{app_port}:{app_port}" in service["ports"]
        assert f"127.0.0.1:{obs_port}:{obs_port}" in service["ports"]

        environment = service["environment"]

        assert environment["NODE_ID"] == node_id
        assert environment["NODE_HOST"] == node_id
        assert str(environment["NODE_PORT"]) == str(app_port)

        assert environment["OBSERVABILITY_HOST"] == "0.0.0.0"
        assert str(environment["OBSERVABILITY_PORT"]) == str(obs_port)

        assert environment["ETCD_ENDPOINTS"] == "http://etcd:2379"
        assert environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4318"


def test_phase6_node_image_contract() -> None:
    dockerfile = Path("deploy/monitoring/Dockerfile.node")

    assert dockerfile.exists()

    text = dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in text
    assert "COPY pyproject.toml README.md ./" in text
    assert "COPY src ./src" in text
    assert "pip install" in text
    assert 'ENTRYPOINT ["python", "-m", "distsys.main"]' in text


def test_phase6_prometheus_scrapes_docker_node_services() -> None:
    config = Path("deploy/monitoring/prometheus/prometheus.yml").read_text(encoding="utf-8")

    for target in (
        "node-0:9100",
        "node-1:9101",
        "node-2:9102",
    ):
        assert target in config

    assert "host.docker.internal:9100" not in config
    assert "host.docker.internal:9101" not in config
    assert "host.docker.internal:9102" not in config


def test_phase6_toxiproxy_uses_docker_node_upstreams() -> None:
    bootstrap = Path("scripts/phase6_proxy_bootstrap.py").read_text(encoding="utf-8")

    assert '"node-0:18000"' in bootstrap
    assert '"node-1:18001"' in bootstrap
    assert '"node-2:18002"' in bootstrap

    assert "host.docker.internal:18000" not in bootstrap
    assert "host.docker.internal:18001" not in bootstrap
    assert "host.docker.internal:18002" not in bootstrap


def test_phase6_runner_does_not_launch_host_node_processes() -> None:
    runner = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    assert '"${COMPOSE[@]}" up -d' in runner
    assert "phase6_start_node.sh" not in runner


def test_phase6_compose_passes_peer_routing_environment_to_nodes() -> None:
    import yaml

    compose = yaml.safe_load(
        Path("deploy/monitoring/docker-compose.yml").read_text(encoding="utf-8")
    )

    for node_id in ("node-0", "node-1", "node-2"):
        environment = compose["services"][node_id]["environment"]

        assert environment["RUN_CHAOS_TESTS"] == "${RUN_CHAOS_TESTS:-}"
        assert environment["PHASE6_PEER_PROXY_MAP"] == "${PHASE6_PEER_PROXY_MAP:-}"


def test_phase6_docker_runner_preserves_direct_and_proxy_routing() -> None:
    runner = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    assert 'PHASE6_PEER_ROUTING="${PHASE6_PEER_ROUTING:-direct}"' in runner

    assert "unset RUN_CHAOS_TESTS" in runner
    assert "unset PHASE6_PEER_PROXY_MAP" in runner

    assert "export RUN_CHAOS_TESTS=1" in runner

    assert "node-0=toxiproxy:19100," "node-1=toxiproxy:19101," "node-2=toxiproxy:19102" in runner

    assert "unsupported PHASE6_PEER_ROUTING" in runner


def test_phase6_runner_manifest_manages_container_nodes() -> None:
    import re

    runner = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    pattern = (
        r'"services"\s*:\s*\['
        r'\s*"etcd"\s*,'
        r'\s*"node-0"\s*,'
        r'\s*"node-1"\s*,'
        r'\s*"node-2"\s*,?'
        r"\s*\]"
    )

    assert re.search(pattern, runner)


def test_phase6_runner_bootstraps_proxies_before_nodes() -> None:
    runner = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    build = '"${COMPOSE[@]}" build node-0 node-1 node-2'

    infrastructure = '"${COMPOSE[@]}" up -d ' "etcd toxiproxy tempo otel-collector"

    bootstrap = "python scripts/phase6_proxy_bootstrap.py"

    nodes = '"${COMPOSE[@]}" up -d ' "node-0 node-1 node-2"

    monitoring = '"${COMPOSE[@]}" up -d ' "prometheus grafana"

    assert build in runner
    assert infrastructure in runner
    assert bootstrap in runner
    assert nodes in runner
    assert monitoring in runner

    assert runner.index(build) < runner.index(infrastructure)
    assert runner.index(infrastructure) < runner.index(bootstrap)
    assert runner.index(bootstrap) < runner.index(nodes)
    assert runner.index(nodes) < runner.index(monitoring)

    assert '"${COMPOSE[@]}" up -d --build' not in runner


def test_phase6_tempo_healthcheck_uses_valid_verify_flag() -> None:
    import yaml

    compose = yaml.safe_load(
        Path("deploy/monitoring/docker-compose.yml").read_text(encoding="utf-8")
    )

    healthcheck = compose["services"]["tempo"]["healthcheck"]["test"]

    assert "-config.verify=true" in healthcheck
    assert "-config.verify" not in healthcheck


def test_phase6_release_gate_waits_for_manifest_before_cluster_ready() -> None:
    import re

    gate = Path("scripts/phase6_release_gate.sh").read_text(encoding="utf-8")

    wait_block = gate[gate.index("wait_for_ready() {") : gate.index("start_cluster() {")]

    pattern = (
        r'if\s+\[\[\s+"\$all"\s+==\s+"1"\s+\]\]'
        r"\s*&&\s*"
        r"\[\[\s+-f\s+"
        r'"\$CURRENT_LOG_DIR/manifest\.json"'
        r"\s+\]\]"
    )

    assert re.search(pattern, wait_block, re.DOTALL)
