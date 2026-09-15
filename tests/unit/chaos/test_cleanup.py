import pytest

from distsys.chaos.safety import CleanupStack


@pytest.mark.asyncio
async def test_cleanup_is_lifo_idempotent_and_continues_after_error():
    events: list[str] = []
    cleanup = CleanupStack()

    async def first():
        events.append("first")

    async def broken():
        events.append("broken")
        raise RuntimeError("x")

    cleanup.push(first)
    cleanup.push(broken)
    errors = await cleanup.run()
    assert events == ["broken", "first"]
    assert len(errors) == 1
    assert await cleanup.run() == []
