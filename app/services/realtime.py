import asyncio
import json
import queue
from threading import Lock
from typing import Any

_subscribers: set[queue.Queue[str]] = set()
_lock = Lock()


def subscribe() -> queue.Queue[str]:
    q: queue.Queue[str] = queue.Queue(maxsize=100)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: queue.Queue[str]) -> None:
    with _lock:
        _subscribers.discard(q)


def publish(event_type: str, payload: dict[str, Any] | None = None) -> None:
    message = json.dumps(
        {"type": event_type, "payload": payload or {}},
        ensure_ascii=False,
        default=str,
    )
    with _lock:
        subscribers = list(_subscribers)
    for q in subscribers:
        try:
            if q.full():
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
            q.put_nowait(message)
        except Exception:
            pass


async def event_stream(q: queue.Queue[str]):
    try:
        yield ": connected\n\n"
        while True:
            try:
                message = await asyncio.to_thread(q.get, True, 25)
                yield f"data: {message}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
    finally:
        unsubscribe(q)
