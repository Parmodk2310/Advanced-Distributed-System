import pytest

from distsys.benchmarking.retry import retry_transport


@pytest.mark.asyncio
async def test_retry_transport_recovers_from_temporary_connection_resets():
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionResetError("temporary reset")
        return "ready"

    result = await retry_transport(operation, attempts=3, delay_seconds=0)

    assert result == "ready"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_transport_reraises_after_attempt_limit():
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        raise ConnectionResetError("persistent reset")

    with pytest.raises(ConnectionResetError, match="persistent reset"):
        await retry_transport(operation, attempts=3, delay_seconds=0)

    assert calls == 3
