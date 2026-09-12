import pytest

from distsys.resilience.rate_limiter import TokenBucketRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_token_bucket_allows_burst_then_rejects():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst=2, clock=clock)

    assert limiter.allow()
    assert limiter.allow()
    assert not limiter.allow()


def test_token_bucket_refills_using_monotonic_elapsed_time():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(rate_per_second=4.0, burst=2, clock=clock)

    assert limiter.allow()
    assert limiter.allow()
    assert not limiter.allow()

    clock.value += 0.25
    assert limiter.allow()
    assert not limiter.allow()


def test_token_bucket_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(rate_per_second=0.0, burst=1)
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(rate_per_second=1.0, burst=0)
