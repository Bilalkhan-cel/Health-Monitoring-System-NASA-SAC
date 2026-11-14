"""In-process pub/sub behind every Server-Sent Events endpoint (Section 10A.7).

* one topic per astronaut, one bounded ``queue.Queue(maxsize=100)`` per subscriber;
* ``publish`` never blocks: when a subscriber's queue is full the oldest message is dropped;
* at most 4 concurrent streams per astronaut (the 5th is refused with 429);
* events queued inside a database transaction are only published after it commits.

Single process only: a multi-worker deployment would need Redis (outside this prototype).
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.orm import Session

MAX_STREAMS_PER_TOPIC = 4
QUEUE_SIZE = 100
KEEPALIVE_S = 15


class TooManyStreams(Exception):
    """Raised when a topic already has the maximum number of subscribers."""


@dataclass(eq=False)
class Subscription:
    topic: str
    queue: "queue.Queue[tuple[str, dict]]" = field(default_factory=lambda: queue.Queue(maxsize=QUEUE_SIZE))


class StreamHub:
    def __init__(self, max_per_topic: int = MAX_STREAMS_PER_TOPIC) -> None:
        self._lock = threading.Lock()
        self._topics: dict[str, set[Subscription]] = {}
        self.max_per_topic = max_per_topic

    @staticmethod
    def topic_for(astronaut_id: int) -> str:
        return f"astronaut:{astronaut_id}"

    def subscribe(self, topic: str) -> Subscription:
        with self._lock:
            subscribers = self._topics.setdefault(topic, set())
            if len(subscribers) >= self.max_per_topic:
                raise TooManyStreams(topic)
            subscription = Subscription(topic)
            subscribers.add(subscription)
            return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            subscribers = self._topics.get(subscription.topic)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    del self._topics[subscription.topic]

    def count(self, topic: str) -> int:
        with self._lock:
            return len(self._topics.get(topic, ()))

    def publish(self, topic: str, event_name: str, data: dict) -> int:
        """Deliver to every subscriber of a topic without blocking. Returns the number reached."""
        with self._lock:
            subscribers = list(self._topics.get(topic, ()))
        for subscription in subscribers:
            message = (event_name, data)
            try:
                subscription.queue.put_nowait(message)
            except queue.Full:
                try:
                    subscription.queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscription.queue.put_nowait(message)
                except queue.Full:
                    pass
        return len(subscribers)

    def publish_to(self, astronaut_id: int, event_name: str, data: dict) -> int:
        return self.publish(self.topic_for(astronaut_id), event_name, data)


def format_sse(event_name: str, data: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def stream(hub: StreamHub, subscription: Subscription, first: list[tuple[str, dict]], keepalive_s: float = KEEPALIVE_S):
    """SSE generator. Touches no database: it only reads hub messages."""
    try:
        for name, data in first:
            yield format_sse(name, data)
        while True:
            try:
                name, data = subscription.queue.get(timeout=keepalive_s)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield format_sse(name, data)
    finally:
        hub.unsubscribe(subscription)


# ── publish after commit ──────────────────────────────────

_PENDING_KEY = "astrovital_pending_events"
_hooks_installed = False


def queue_event(session: Session, astronaut_id: int, event_name: str, data: dict,
                hub: StreamHub | None = None) -> None:
    """Publish when the surrounding transaction commits (dropped on rollback)."""
    if hub is None:
        from flask import current_app, has_app_context

        runtime = current_app.extensions.get("live") if has_app_context() else None
        if runtime is None:
            return
        hub = runtime.hub
    session.info.setdefault(_PENDING_KEY, []).append((hub, astronaut_id, event_name, data))


def install_session_hooks() -> None:
    """Install the after-commit publisher once per process (all apps share it)."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    @event.listens_for(Session, "after_commit")
    def _after_commit(session):  # noqa: ANN001
        pending = session.info.pop(_PENDING_KEY, [])
        merged: dict[tuple[int, int], tuple[StreamHub, int, list[str]]] = {}
        for hub, astronaut_id, name, data in pending:
            if name == "summary":
                key = (id(hub), astronaut_id)
                metrics = merged.setdefault(key, (hub, astronaut_id, []))[2]
                metrics.extend(metric for metric in data.get("metrics", []) if metric not in metrics)
            else:
                hub.publish_to(astronaut_id, name, data)
        for hub, astronaut_id, metrics in merged.values():
            hub.publish_to(astronaut_id, "summary", {"metrics": metrics})

    @event.listens_for(Session, "after_rollback")
    def _after_rollback(session):  # noqa: ANN001
        session.info.pop(_PENDING_KEY, None)
