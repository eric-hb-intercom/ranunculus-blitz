"""Poller: schedules diff cycles at regular intervals."""

from __future__ import annotations

import asyncio
import logging

from .differ import run_diff_cycle
from .superlatives import compute_superlatives

logger = logging.getLogger(__name__)

# Global flag to control the poller
_running = False
_task: asyncio.Task | None = None


async def start_poller(interval: int, broadcast_fn) -> None:
    """Start the diff polling loop."""
    global _running, _task
    if _running:
        logger.warning("Poller already running")
        return

    _running = True
    _task = asyncio.current_task() or asyncio.ensure_future(
        _poll_loop(interval, broadcast_fn)
    )
    if asyncio.current_task():
        await _poll_loop(interval, broadcast_fn)


async def stop_poller() -> None:
    """Stop the diff polling loop."""
    global _running, _task
    _running = False
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("Poller stopped")


def is_running() -> bool:
    return _running


async def _poll_loop(interval: int, broadcast_fn) -> None:
    """Main polling loop."""
    global _running
    logger.info(f"Poller started (interval: {interval}s)")

    while _running:
        try:
            events = await run_diff_cycle()
            await compute_superlatives()

            if events or True:  # Always broadcast (for timer updates)
                await broadcast_fn({
                    "type": "diff_complete",
                    "new_events_count": len(events),
                })

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in diff cycle: {e}", exc_info=True)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break

    _running = False
    logger.info("Poller loop exited")
