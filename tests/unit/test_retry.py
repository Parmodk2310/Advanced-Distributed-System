import pytest

from distsys.resilience.deadline import DeadlineExceeded
from distsys.resilience.retry import RetryPolicy, retry_async


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    attempts = 0
    sleeps: list[float] = []

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary")
        return "ok"

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    values = iter([0.25, 0.5])

    result = await retry_async(
        operation,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0),
        should_retry=lambda exc: isinstance(exc, ConnectionError),
        random_fn=lambda low, high: next(values) * high,
        sleep_fn=fake_sleep,
    )

    assert result == "ok"
    assert attempts == 3
    assert sleeps == pytest.approx([0.025, 0.1])


@pytest.mark.asyncio
async def test_retry_stops_after_max_attempts():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("still down")

    async def fake_sleep(_: float) -> None:
        return None

    with pytest.raises(ConnectionError, match="still down"):
        await retry_async(
            operation,
            policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=1.0),
            should_retry=lambda exc: True,
            random_fn=lambda low, high: 0.0,
            sleep_fn=fake_sleep,
        )

    assert attempts == 2


@pytest.mark.asyncio
async def test_retry_does_not_retry_non_retryable_exception():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        await retry_async(
            operation,
            policy=RetryPolicy(max_attempts=4),
            should_retry=lambda exc: isinstance(exc, ConnectionError),
        )

    assert attempts == 1


@pytest.mark.asyncio
async def test_retry_respects_expired_deadline_before_first_attempt():
    class ExpiredDeadline:
        def expired(self) -> bool:
            return True

        def remaining(self) -> float:
            return 0.0

    async def operation():
        return "never"

    with pytest.raises(DeadlineExceeded):
        await retry_async(
            operation,
            policy=RetryPolicy(max_attempts=3),
            should_retry=lambda exc: True,
            deadline=ExpiredDeadline(),  # type: ignore[arg-type]
        )
