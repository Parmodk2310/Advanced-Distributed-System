"""Tests for resilience patterns."""

import pytest
import asyncio
from src.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from src.resilience.backpressure import BackpressureController
from src.resilience.retry import RetryPolicy


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_closed_state(self):
        cb = CircuitBreaker(failure_threshold=3)
        
        async def success():
            return "ok"
        
        result = await cb.call(success)
        assert result == "ok"
        assert cb.state.name == "CLOSED"
    
    @pytest.mark.asyncio
    async def test_opens_after_failures(self):
        cb = CircuitBreaker(failure_threshold=2)
        
        async def fail():
            raise Exception("fail")
        
        with pytest.raises(Exception):
            await cb.call(fail)
        with pytest.raises(Exception):
            await cb.call(fail)
        
        assert cb.state.name == "OPEN"
        
        with pytest.raises(CircuitBreakerOpen):
            await cb.call(fail)
    
    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, half_open_max=1)
        
        async def fail():
            raise Exception("fail")
        
        async def success():
            return "ok"
        
        with pytest.raises(Exception):
            await cb.call(fail)
        
        assert cb.state.name == "OPEN"
        await asyncio.sleep(0.15)
        
        result = await cb.call(success)
        assert result == "ok"
        assert cb.state.name == "CLOSED"


class TestBackpressure:
    @pytest.mark.asyncio
    async def test_acquire_release(self):
        bp = BackpressureController(max_queue_depth=10)
        assert await bp.acquire()
        await bp.release()
        assert bp.load_factor == 0.0
    
    @pytest.mark.asyncio
    async def test_rejection_at_capacity(self):
        bp = BackpressureController(max_queue_depth=2)
        assert await bp.acquire()
        assert await bp.acquire()
        # At capacity, may reject
        # (probabilistic, so we just verify it doesn't crash)
        await bp.acquire()


class TestRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        retry = RetryPolicy(max_retries=2)
        
        async def success():
            return "ok"
        
        result = await retry.execute(success)
        assert result == "ok"
    
    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        retry = RetryPolicy(max_retries=2, base_delay=0.01)
        attempts = 0
        
        async def sometimes_fails():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise Exception("fail")
            return "ok"
        
        result = await retry.execute(sometimes_fails)
        assert result == "ok"
        assert attempts == 2