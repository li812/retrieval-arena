import asyncio
import contextvars
import json
import queue
from collections.abc import AsyncGenerator, Callable
from threading import Thread

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def start_thread(target: Callable[[], None]) -> None:
    """Daemon thread that keeps the caller's context (request_id, run_id) for its log lines."""
    Thread(target=contextvars.copy_context().run, args=(target,), daemon=True).start()


async def drain(gen_factory, result: dict) -> AsyncGenerator[tuple[str, dict], None]:
    """Run a blocking (event, data) generator in a worker thread and relay its items as they arrive.

    The generator's return value is stored in result["value"].
    """
    q: queue.SimpleQueue = queue.SimpleQueue()
    end = object()

    def worker():
        try:
            gen = gen_factory()
            while True:
                try:
                    q.put(next(gen))
                except StopIteration as stop:
                    result["value"] = stop.value or {}
                    break
        except Exception as exc:
            q.put(("error", {"message": str(exc)}))
        finally:
            q.put(end)

    start_thread(worker)
    while True:
        item = await asyncio.to_thread(q.get)
        if item is end:
            break
        yield item
