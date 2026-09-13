import pytest

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import (
    PeerApplicationError,
    PeerClient,
    PeerTransportError,
)
from distsys.proto import messages_pb2
from distsys.protocol.codec import encode_task_response
from distsys.protocol.message import Message, MessageType
from distsys.resilience.circuit_breaker import CircuitOpenError
from distsys.resilience.deadline import Deadline
from distsys.resilience.retry import RetryPolicy


def member(node_id: str = "node-1", port: int = 18001) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


class ScriptedPeerClient(PeerClient):
    def __init__(self, script, *, threshold: int = 5):
        super().__init__(
            local_node_id="node-0",
            retry_policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
            ),
            circuit_breaker_failure_threshold=threshold,
            circuit_breaker_recovery_seconds=60.0,
        )
        self.script = list(script)
        self.calls = 0
        self.correlation_ids: list[str] = []

    async def _exchange_endpoint(
        self,
        host,
        port,
        message,
        *,
        timeout_seconds,
    ):
        self.calls += 1
        self.correlation_ids.append(message.correlation_id)
        outcome = self.script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def response_factory(result):
    class DynamicClient(ScriptedPeerClient):
        async def _exchange_endpoint(
            self,
            host,
            port,
            message,
            *,
            timeout_seconds,
        ):
            self.calls += 1
            self.correlation_ids.append(message.correlation_id)
            outcome = self.script.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome == "success":
                return Message.new_response(
                    sender_id="node-1",
                    correlation_id=message.correlation_id,
                    payload=encode_task_response(success=True, result=result),
                )
            if outcome == "invalid":
                return Message.new_response(
                    sender_id="node-1",
                    correlation_id=message.correlation_id,
                    payload=encode_task_response(
                        success=False,
                        error_code=messages_pb2.INVALID_REQUEST,
                        error_message="bad payload",
                    ),
                    msg_type=MessageType.ERROR,
                )
            return outcome

    return DynamicClient


@pytest.mark.asyncio
async def test_forward_task_retries_transport_failures_and_reuses_correlation_id():
    client_type = response_factory({"ok": True})
    client = client_type([ConnectionRefusedError(), TimeoutError(), "success"])

    result = await client.forward_task(
        member(),
        task_name="echo",
        payload={"x": 1},
        routing_key="key",
        origin_node_id="node-0",
        deadline=Deadline.after(1.0),
    )

    assert result == {"ok": True}
    assert client.calls == 3
    assert len(set(client.correlation_ids)) == 1


@pytest.mark.asyncio
async def test_structured_application_error_does_not_retry_or_trip_transport_breaker():
    client_type = response_factory(None)
    client = client_type(["invalid"], threshold=1)

    with pytest.raises(PeerApplicationError) as exc:
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )

    assert exc.value.code == messages_pb2.INVALID_REQUEST
    assert client.calls == 1
    assert client.breaker_for("node-1").failure_count == 0


@pytest.mark.asyncio
async def test_exhausted_transport_failures_raise_peer_transport_error():
    client = ScriptedPeerClient(
        [
            ConnectionRefusedError(),
            ConnectionRefusedError(),
            ConnectionRefusedError(),
        ]
    )

    with pytest.raises(PeerTransportError):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )

    assert client.calls == 3


@pytest.mark.asyncio
async def test_open_circuit_refuses_follow_up_call_without_exchange():
    client = ScriptedPeerClient([ConnectionRefusedError()], threshold=1)

    with pytest.raises(CircuitOpenError):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )
    assert client.calls == 1

    with pytest.raises(CircuitOpenError):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key2",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )
    assert client.calls == 1


@pytest.mark.asyncio
async def test_control_ping_is_single_attempt_without_task_retry():
    client = ScriptedPeerClient([ConnectionRefusedError()])

    with pytest.raises(ConnectionRefusedError):
        await client.ping(member(), (), timeout_seconds=0.1)

    assert client.calls == 1
