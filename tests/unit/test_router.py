import pytest

from distsys.compute.router import TaskRouter, UnknownTaskError


@pytest.mark.asyncio
async def test_router_dispatches_async_handler():
    router = TaskRouter()

    async def handler(payload):
        return {"received": payload}

    router.register("demo", handler)
    assert await router.dispatch("demo", 7) == {"received": 7}


@pytest.mark.asyncio
async def test_unknown_task_raises():
    router = TaskRouter()
    with pytest.raises(UnknownTaskError):
        await router.dispatch("missing", None)
