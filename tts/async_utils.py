"""
Bridges a synchronous generator (e.g. Piper.stream(), which blocks)
into something an async gRPC servicer can iterate without blocking
the event loop.
"""

import asyncio
import threading

_SENTINEL = object()


async def iter_in_thread(sync_gen_func, *args):
    """Runs sync_gen_func(*args) - a blocking generator - in a
    background thread, yielding its items asynchronously as they're
    produced."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    loop = asyncio.get_event_loop()

    def producer():
        try:
            for item in sync_gen_func(*args):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    threading.Thread(target=producer, daemon=True).start()

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        yield item
