from __future__ import annotations

import math
import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AccountStatsLoopConfig:
    interval_sec: float
    tick_sec: float
    worker_shutdown_timeout_sec: float = 0.05


@dataclass(frozen=True)
class AccountStatsRefreshStartedEvent:
    refresh_id: int


@dataclass(frozen=True)
class AccountStatsRefreshPayloadEvent:
    refresh_id: int
    payload: dict[str, object]


@dataclass(frozen=True)
class AccountStatsRefreshErrorEvent:
    refresh_id: int
    error: Exception


@dataclass(frozen=True)
class AccountStatsRefreshDoneEvent:
    refresh_id: int


AccountStatsRefreshEvent = (
    AccountStatsRefreshStartedEvent
    | AccountStatsRefreshPayloadEvent
    | AccountStatsRefreshErrorEvent
    | AccountStatsRefreshDoneEvent
)


AccountStatsLoopState = Literal["idle", "refreshing", "refresh_queued", "stopping"]


@dataclass(frozen=True)
class AccountStatsLoopSnapshot:
    state: AccountStatsLoopState
    interval_sec: float
    status_text: str
    refresh_id: int | None = None
    started_at_monotonic: float | None = None
    finished_at_monotonic: float | None = None
    next_refresh_at_monotonic: float | None = None
    refresh_queued: bool = False
    body_text: str = ""
    refresh_progress_text: str | None = None
    refresh_error_text: str | None = None

    @property
    def refreshing(self) -> bool:
        return self.state in ("refreshing", "refresh_queued")

    @property
    def refresh_requested(self) -> bool:
        return self.refresh_queued

    def remaining_refresh_sec(self, *, now_monotonic: float) -> float:
        if self.next_refresh_at_monotonic is None:
            return 0.0
        return max(0.0, self.next_refresh_at_monotonic - now_monotonic)

    def render_text(self, *, now_monotonic: float | None = None) -> str:
        del now_monotonic
        sections: list[str] = [self.status_text]
        if self.refresh_progress_text is not None:
            sections.append(self.refresh_progress_text)
        if self.refresh_error_text is not None:
            sections.append(self.refresh_error_text)
        sections.append(self.body_text or "[loop] refreshing...")
        return "\n\n".join(sections)


class AccountStatsRefreshWorker:
    def __init__(
        self,
        *,
        refresh_id: int,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> None:
        self.refresh_id = refresh_id
        self._payloads = payloads
        self._stop_requested = threading.Event()
        self.events: queue.Queue[AccountStatsRefreshEvent] = queue.Queue()
        self.thread = threading.Thread(
            target=self._run,
            name=f"agentos-agent-accounts-refresh-{refresh_id}",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def shutdown(self, *, timeout_sec: float) -> None:
        self.request_stop()
        self.thread.join(timeout=timeout_sec)

    def _run(self) -> None:
        try:
            self.events.put(AccountStatsRefreshStartedEvent(refresh_id=self.refresh_id))
            for payload in self._payloads():
                if self._stop_requested.is_set():
                    break
                self.events.put(
                    AccountStatsRefreshPayloadEvent(
                        refresh_id=self.refresh_id,
                        payload=payload,
                    )
                )
                if self._stop_requested.is_set():
                    break
        except Exception as exc:
            if not self._stop_requested.is_set():
                self.events.put(
                    AccountStatsRefreshErrorEvent(
                        refresh_id=self.refresh_id,
                        error=exc,
                    )
                )
        finally:
            self.events.put(AccountStatsRefreshDoneEvent(refresh_id=self.refresh_id))


class AccountStatsLoopController:
    def __init__(
        self,
        *,
        config: AccountStatsLoopConfig,
        render_payload: Callable[[dict[str, object]], str] | None = None,
        render_progress: Callable[[dict[str, object]], str | None] | None = None,
        render_error_status: Callable[[Exception], str] | None = None,
        render_error_body: Callable[[Exception], str] | None = None,
        worker_factory: Callable[
            [int, Callable[[], Iterator[dict[str, object]]]],
            AccountStatsRefreshWorker,
        ]
        | None = None,
    ) -> None:
        self.config = config
        self.state: AccountStatsLoopState = "idle"
        self._next_refresh_id = 1
        self._render_payload = render_payload or _default_render_payload
        self._render_progress = render_progress or _default_render_progress
        self._render_error_status = render_error_status or _default_render_error_status
        self._render_error_body = render_error_body or _default_render_error_body
        self._worker_factory = worker_factory or _default_worker_factory
        self.refresh_worker: AccountStatsRefreshWorker | None = None
        self.refresh_id: int | None = None
        self.started_at_monotonic: float | None = None
        self.finished_at_monotonic: float | None = None
        self.next_refresh_at_monotonic: float | None = None
        self.refresh_queued = False
        self.body_text = ""
        self.refresh_progress_text: str | None = None
        self.refresh_error_text: str | None = None

    def start(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> AccountStatsRefreshWorker:
        return self._start_refresh(now_monotonic=now_monotonic, payloads=payloads)

    def tick(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> bool:
        if self.refresh_worker is not None:
            return False
        if self.next_refresh_at_monotonic is not None and now_monotonic < self.next_refresh_at_monotonic:
            return False
        self._start_refresh(now_monotonic=now_monotonic, payloads=payloads)
        return True

    def request_refresh(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> bool:
        if self.refresh_worker is None:
            self._start_refresh(now_monotonic=now_monotonic, payloads=payloads)
            return True
        changed = not self.refresh_queued
        self.refresh_queued = True
        self.state = "refresh_queued"
        return changed

    def drain_worker_events(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> bool:
        worker = self.refresh_worker
        if worker is None:
            return False

        changed = False
        while True:
            try:
                event = worker.events.get_nowait()
            except queue.Empty:
                break
            changed = self.handle_worker_event(
                event,
                now_monotonic=now_monotonic,
                payloads=payloads,
            ) or changed
            worker = self.refresh_worker
            if worker is None:
                break
        return changed

    def handle_worker_event(
        self,
        event: AccountStatsRefreshEvent,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> bool:
        if self.refresh_worker is None or event.refresh_id != self.refresh_worker.refresh_id:
            return False

        if isinstance(event, AccountStatsRefreshStartedEvent):
            return False
        if isinstance(event, AccountStatsRefreshPayloadEvent):
            self.body_text = self._render_payload(event.payload)
            self.refresh_progress_text = self._render_progress(event.payload)
            self.refresh_error_text = None
            return True
        if isinstance(event, AccountStatsRefreshErrorEvent):
            self.refresh_progress_text = None
            self.refresh_error_text = self._render_error_status(event.error)
            if not self.body_text or self.body_text == "[loop] refreshing...":
                self.body_text = self._render_error_body(event.error)
            self._finish_refresh(now_monotonic=now_monotonic, payloads=payloads)
            return True

        self._finish_refresh(now_monotonic=now_monotonic, payloads=payloads)
        return True

    def wait_timeout(self, *, now_monotonic: float) -> float:
        if self.refresh_worker is not None:
            return self.config.tick_sec
        if self.next_refresh_at_monotonic is None:
            return 0.0
        remaining_sec = max(0.0, self.next_refresh_at_monotonic - now_monotonic)
        return min(self.config.tick_sec, remaining_sec)

    def snapshot(self, *, now_monotonic: float) -> AccountStatsLoopSnapshot:
        return AccountStatsLoopSnapshot(
            state=self.state,
            interval_sec=self.config.interval_sec,
            status_text=self._status_text(now_monotonic=now_monotonic),
            refresh_id=self.refresh_id,
            started_at_monotonic=self.started_at_monotonic,
            finished_at_monotonic=self.finished_at_monotonic,
            next_refresh_at_monotonic=self.next_refresh_at_monotonic,
            refresh_queued=self.refresh_queued,
            body_text=self.body_text,
            refresh_progress_text=self.refresh_progress_text,
            refresh_error_text=self.refresh_error_text,
        )

    def shutdown(self) -> None:
        self.state = "stopping"
        if self.refresh_worker is not None:
            self.refresh_worker.shutdown(timeout_sec=self.config.worker_shutdown_timeout_sec)
            self.refresh_worker = None
        self.refresh_id = None

    def _start_refresh(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> AccountStatsRefreshWorker:
        refresh_id = self._next_refresh_id
        self._next_refresh_id += 1
        worker = self._worker_factory(refresh_id, payloads)
        self.refresh_worker = worker
        self.refresh_id = refresh_id
        self.state = "refreshing"
        self.started_at_monotonic = now_monotonic
        self.finished_at_monotonic = None
        self.next_refresh_at_monotonic = None
        self.refresh_queued = False
        self.refresh_progress_text = None
        self.refresh_error_text = None
        if not self.body_text:
            self.body_text = "[loop] refreshing..."
        worker.start()
        return worker

    def _finish_refresh(
        self,
        *,
        now_monotonic: float,
        payloads: Callable[[], Iterator[dict[str, object]]],
    ) -> None:
        queued_refresh = self.refresh_queued
        self.refresh_worker = None
        self.refresh_id = None
        self.finished_at_monotonic = now_monotonic
        self.refresh_progress_text = None

        if queued_refresh:
            self._start_refresh(now_monotonic=now_monotonic, payloads=payloads)
            return

        self.state = "idle"
        self.refresh_queued = False
        self.next_refresh_at_monotonic = now_monotonic + self.config.interval_sec

    def _status_text(self, *, now_monotonic: float) -> str:
        interval_text = f"{int(self.config.interval_sec)}s"
        if self.refresh_worker is not None:
            if self.refresh_queued:
                return f"[loop] refreshing... queued another refresh; fixed-delay {interval_text}; Ctrl-C to stop"
            return f"[loop] refreshing... fixed-delay {interval_text}; Enter queues another refresh; Ctrl-C to stop"
        if self.next_refresh_at_monotonic is None:
            return (
                f"[loop] fixed-delay {interval_text} after each refresh; "
                "press Enter to refresh now; Ctrl-C to stop"
            )
        remaining_text = _format_loop_countdown(self.next_refresh_at_monotonic - now_monotonic)
        return (
            f"[loop] fixed-delay {interval_text} after each refresh; next refresh in {remaining_text}; "
            "press Enter to refresh now; Ctrl-C to stop"
        )


def _default_worker_factory(
    refresh_id: int,
    payloads: Callable[[], Iterator[dict[str, object]]],
) -> AccountStatsRefreshWorker:
    return AccountStatsRefreshWorker(refresh_id=refresh_id, payloads=payloads)


def _default_render_payload(payload: dict[str, object]) -> str:
    return str(payload)


def _default_render_progress(payload: dict[str, object]) -> str | None:
    del payload
    return None


def _default_render_error_status(error: Exception) -> str:
    return f"[refresh] error: {_default_error_message(error)}"


def _default_render_error_body(error: Exception) -> str:
    return "\n".join(
        [
            "# Agent Accounts Usage",
            "",
            "refresh | error",
            f"   | {_default_error_message(error)}",
        ]
    )


def _default_error_message(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return message
    return error.__class__.__name__


def _format_loop_countdown(remaining_sec: float) -> str:
    total_seconds = max(0, math.ceil(remaining_sec))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
