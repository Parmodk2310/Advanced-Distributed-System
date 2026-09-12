"""Application bootstrap only."""

from __future__ import annotations

import asyncio
import signal

from distsys.node import DistributedNode
from distsys.utils.config import Settings
from distsys.utils.logging import configure_logging


async def run() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    node = DistributedNode(settings)
    await node.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        await node.stop()


def cli() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    cli()
