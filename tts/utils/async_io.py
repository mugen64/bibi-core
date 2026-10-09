"""
Bridges a synchronous generator (e.g. PiperEngine.stream(), which blocks)
into something an async gRPC servicer can iterate without blocking
the event loop.
"""

import asyncio
import queue
import threading

_SENTINEL = object()


async def iter_in_thread(sync_gen_func, *args):
    """Runs sync_gen_func(*args) - a blocking generator - in a
    background thread, yielding its items asynchronously as they're
    produced."""
    items: queue.Queue = queue.Queue(maxsize=8)
    stopped = threading.Event()

    def enqueue(item):
        while not stopped.is_set():
            try:
                items.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def producer():
        try:
            for item in sync_gen_func(*args):
                if stopped.is_set():
                    break
                enqueue((True, item))
        except Exception as exc:
            enqueue((False, exc))
        finally:
            enqueue((True, _SENTINEL))

    threading.Thread(target=producer, daemon=True).start()

    try:
        while True:
            try:
                succeeded, item = items.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.001)
                continue
            if not succeeded:
                raise item
            if item is _SENTINEL:
                break
            yield item
    finally:
        stopped.set()
