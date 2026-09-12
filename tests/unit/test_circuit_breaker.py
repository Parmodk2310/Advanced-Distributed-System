import pytest

from distsys.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_circuit_opens_after_failure_threshold():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=10.0, clock=clock)

    async def fail():
        raise ConnectionError("down")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await breaker.call(fail)

    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await breaker.call(fail)


@pytest.mark.asyncio
async def test_half_open_success_closes_breaker():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=5.0, clock=clock)

    async def fail():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await breaker.call(fail)
    assert breaker.state is CircuitState.OPEN

    clock.value = 5.0

    async def succeed():
        return "ok"

    assert await breaker.call(succeed) == "ok"
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_breaker():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=5.0, clock=clock)

    async def fail():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await breaker.call(fail)

    clock.value = 5.0
    with pytest.raises(ConnectionError):
        await breaker.call(fail)

    assert breaker.state is CircuitState.OPEN


def test_circuit_breaker_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0)
