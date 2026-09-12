import asyncio

import pytest

from distsys.resilience.deadline import Deadline, DeadlineExceeded


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_deadline_tracks_remaining_budget():
    clock = FakeClock()
    deadline = Deadline.after(5.0, clock=clock)
    assert deadline.remaining() == pytest.approx(5.0)

    clock.value += 1.25
    assert deadline.remaining() == pytest.approx(3.75)
    assert not deadline.expired()

    clock.value += 4.0
    assert deadline.remaining() == 0.0
    assert deadline.expired()


@pytest.mark.asyncio
async def test_deadline_run_raises_when_operation_exceeds_budget():
    deadline = Deadline.after(0.01)
    with pytest.raises(DeadlineExceeded):
        await deadline.run(asyncio.sleep(0.05))
