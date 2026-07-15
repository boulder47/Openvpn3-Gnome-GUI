"""Bridges asyncio coroutines with the GLib main loop used by GTK4.

GTK4 applications run inside ``GLib.MainLoop``. Rather than run a second,
competing asyncio loop, we drive a single asyncio event loop *on top of*
GLib's loop using ``gbulb``-style integration implemented locally (to avoid
an extra hard dependency): a recurring ``GLib.idle_add`` pump drains ready
asyncio callbacks. This keeps the whole app single-threaded and avoids GTK
thread-safety pitfalls, while letting services/openvpn code use ``async def``
and ``asyncio.create_subprocess_exec`` freely.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

logger = logging.getLogger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None


def get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide asyncio loop, creating it on first use."""

    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        GLib.timeout_add(15, _pump_loop)
    return _loop


def _pump_loop() -> bool:
    """Run one non-blocking iteration of the asyncio loop from a GLib timeout."""

    loop = _loop
    assert loop is not None  # noqa: S101 - pump only scheduled after loop creation
    loop.call_soon(loop.stop)
    loop.run_forever()
    return True  # keep the GLib timeout alive


def run_async(coro: Coroutine[Any, Any, T], on_done=None, on_error=None) -> asyncio.Task:  # noqa: UP047
    """Schedule a coroutine on the shared loop from GTK signal handlers.

    ``on_done(result)`` and ``on_error(exception)`` are invoked back on the
    GLib main loop, so they may safely touch widgets.
    """

    loop = get_or_create_loop()
    task = loop.create_task(coro)

    def _finished(t: asyncio.Task) -> None:
        try:
            result = t.result()
        except asyncio.CancelledError:
            logger.debug("Task cancelled: %s", coro)
        except Exception as exc:  # noqa: BLE001 - surfaced to caller
            logger.exception("Async task failed")
            if on_error is not None:
                GLib.idle_add(on_error, exc)
        else:
            if on_done is not None:
                GLib.idle_add(on_done, result)

    task.add_done_callback(_finished)
    return task
