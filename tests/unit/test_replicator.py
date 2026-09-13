import asyncio

import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter
from distsys.replication.outbox import ReplicationOutbox
from distsys.replication.replicator import Replicator
from distsys.resilience.retry import RetryPolicy
from distsys.storage import StoredCrdtEntry


def entry(n: int) -> StoredCrdtEntry:
    actor = CausalActor("node-0", 1)
    vv = VersionVector().with_dot(Dot(actor, n))
    return StoredCrdtEntry(
        "views",
        CrdtType.GCOUNTER,
        GCounter().increment(actor, n),
        vv,
        vv,
    )


class RecordingTransport:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[tuple[str, StoredCrdtEntry]] = []
        self.called = asyncio.Event()

    async def send_state(self, peer_node_id: str, state: StoredCrdtEntry) -> None:
        self.calls.append((peer_node_id, state))
        self.called.set()
        if self.failures:
            self.failures -= 1
            raise ConnectionRefusedError("offline")


@pytest.mark.asyncio
async def test_successful_send_clears_matching_generation():
    outbox = ReplicationOutbox(capacity=2)
    transport = RecordingTransport()
    replicator = Replicator(
        outbox,
        transport,
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
    )
    reservation = await outbox.reserve((("node-1", "views"),))
    await outbox.publish(reservation, {"views": entry(1)})
    await replicator.start()
    await asyncio.wait_for(transport.called.wait(), timeout=0.5)
    for _ in range(20):
        if await outbox.pending_count() == 0:
            break
        await asyncio.sleep(0.01)
    await replicator.stop()
    assert await outbox.pending_count() == 0
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_transport_failure_uses_bounded_retry_then_abandons():
    outbox = ReplicationOutbox(capacity=2)
    transport = RecordingTransport(failures=10)
    replicator = Replicator(
        outbox,
        transport,
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
    )
    reservation = await outbox.reserve((("node-1", "views"),))
    await outbox.publish(reservation, {"views": entry(1)})
    await replicator.start()
    for _ in range(50):
        if len(transport.calls) >= 3 and await outbox.pending_count() == 0:
            break
        await asyncio.sleep(0.01)
    await replicator.stop()
    assert len(transport.calls) == 3
    assert await outbox.pending_count() == 0


@pytest.mark.asyncio
async def test_new_generation_is_sent_after_old_inflight_send():
    outbox = ReplicationOutbox(capacity=2)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[int] = []

    class BlockingTransport:
        async def send_state(self, peer_node_id: str, state: StoredCrdtEntry) -> None:
            calls.append(state.state.value())  # type: ignore[union-attr]
            if len(calls) == 1:
                entered.set()
                await release.wait()

    replicator = Replicator(
        outbox,
        BlockingTransport(),
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
    )
    r1 = await outbox.reserve((("node-1", "views"),))
    await outbox.publish(r1, {"views": entry(1)})
    await replicator.start()
    await asyncio.wait_for(entered.wait(), timeout=0.5)

    r2 = await outbox.reserve((("node-1", "views"),))
    await outbox.publish(r2, {"views": entry(2)})
    release.set()
    for _ in range(50):
        if calls == [1, 2] and await outbox.pending_count() == 0:
            break
        await asyncio.sleep(0.01)
    await replicator.stop()
    assert calls == [1, 2]
