"""Prepare lessons and first check questions ahead of the student (docs/35).

One daemon thread works through a de-duplicated queue, so the student rarely
waits for the local model. Jobs share the service's generation lock, so at most
one model call runs at a time. Status is kept in memory: after a restart,
anything already generated is in the store, and missing work is scheduled again
on the next trigger.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

JobKey = tuple[str, int, str, str]  # course_id, revision, topic_id, "lesson"|"questions"


class PreparationWorkerV01:
    def __init__(self, run_job: Callable[[JobKey], None], *, background: bool = True) -> None:
        self._run_job = run_job
        self._background = background
        self._queue: queue.Queue[JobKey] = queue.Queue()
        self._lock = threading.Lock()
        self._status: dict[JobKey, dict] = {}
        # Seconds the last finished job of each kind took on this computer, so
        # the page can say how long a wait really is (memory pressure varies).
        self._last_seconds: dict[str, int] = {}
        if background:
            threading.Thread(target=self._loop, name="urpp-preparation", daemon=True).start()

    def submit(self, key: JobKey) -> None:
        with self._lock:
            if self._status.get(key, {}).get("state") in ("queued", "working"):
                return
            self._status[key] = {"state": "queued", "since": time.time()}
        if self._background:
            self._queue.put(key)
        else:
            self._work(key)

    def status(self, key: JobKey) -> dict | None:
        with self._lock:
            entry = self._status.get(key)
            if entry is None:
                return None
            return {**entry, "seconds": round(time.time() - entry["since"])}

    def busy(self, course_id: str, revision: int) -> bool:
        with self._lock:
            return any(
                key[0] == course_id and key[1] == revision
                and entry["state"] in ("queued", "working")
                for key, entry in self._status.items()
            )

    def last_seconds(self) -> dict[str, int]:
        with self._lock:
            return dict(self._last_seconds)

    def _loop(self) -> None:
        while True:
            self._work(self._queue.get())

    def _work(self, key: JobKey) -> None:
        started = time.time()
        with self._lock:
            self._status[key] = {"state": "working", "since": started}
        try:
            self._run_job(key)
            state, error = "ready", None
        except Exception as exc:  # noqa: BLE001 - reported to the UI, never fatal
            state, error = "failed", type(exc).__name__
        with self._lock:
            self._status[key] = {"state": state, "since": time.time(), "error": error}
            if state == "ready":
                self._last_seconds[key[3]] = round(time.time() - started)
