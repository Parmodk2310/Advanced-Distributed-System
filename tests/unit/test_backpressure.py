import pytest

from distsys.resilience.backpressure import BackpressureController


@pytest.mark.asyncio
async def test_backpressure_rejects_when_capacity_is_full():
    controller = BackpressureController(capacity=2)

    assert await controller.try_acquire()
    assert await controller.try_acquire()
    assert not await controller.try_acquire()
    assert controller.in_flight == 2

    await controller.release()
    assert await controller.try_acquire()


@pytest.mark.asyncio
async def test_backpressure_release_cannot_underflow():
    controller = BackpressureController(capacity=1)
    with pytest.raises(RuntimeError, match="underflow"):
        await controller.release()
