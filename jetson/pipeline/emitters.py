"""Pipeline result emitters.

An emitter is anything that consumes a `PipelineResult` and surfaces it
somewhere. Four implementations:

  StdoutEmitter         — one human-readable line per result
  JSONLinesEmitter      — one JSON object per result (pipe-friendly)
  TCPSocketEmitter      — one JSON object per result over a TCP socket
  LiveDashboardEmitter  — full-screen rich terminal dashboard, in-place
                           updates, includes a motion-score sparkline
"""

from __future__ import annotations

import json
import logging
import random
import socket
import sys
from collections import deque
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import IO, Optional, Protocol

from jetson.pipeline.orchestrator import PipelineResult

logger = logging.getLogger(__name__)


class Emitter(Protocol):
    def emit(self, result: PipelineResult) -> None: ...
    def close(self) -> None: ...


def pipeline_result_to_payload(result: PipelineResult) -> dict[str, object | None]:
    return {
        "timestamp_us": result.timestamp_us,
        "breath_rate_bpm": (
            result.breath_rate.rate_bpm if result.breath_rate else None
        ),
        "breath_confidence": (
            result.breath_rate.confidence if result.breath_rate else None
        ),
        "motion_state": result.motion.state.value if result.motion else None,
        "motion_score": result.motion.motion_score if result.motion else None,
    }


class StdoutEmitter:
    def __init__(self, stream: IO[str] = sys.stdout) -> None:
        self._stream = stream

    def emit(self, result: PipelineResult) -> None:
        t = result.timestamp_us / 1_000_000.0
        if result.breath_rate is not None:
            b = f"{result.breath_rate.rate_bpm:.1f} bpm (conf {result.breath_rate.confidence:.0f}x)"
        else:
            b = "—"
        if result.motion is not None:
            m = f"{result.motion.state.value} (score {result.motion.motion_score:.2f})"
        else:
            m = "—"
        print(f"[t={t:7.2f}s] breath: {b}  |  motion: {m}", file=self._stream)

    def close(self) -> None:
        self._stream.flush()


class JSONLinesEmitter:
    def __init__(self, stream: IO[str] = sys.stdout) -> None:
        self._stream = stream

    def emit(self, result: PipelineResult) -> None:
        self._stream.write(json.dumps(pipeline_result_to_payload(result)) + "\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.flush()


@dataclass(frozen=True)
class TCPSocketEmitterStats:
    connected: bool
    connect_attempts: int
    reconnects: int
    dropped_results: int
    last_backoff_s: float


class TCPSocketEmitter:
    """Streams pipeline results as JSON lines over TCP.

    Transport failures never propagate into the pipeline loop. A background
    connector thread owns all DNS and connect work and applies exponential
    backoff between failed attempts, so `emit` never connects and never
    blocks: results produced while disconnected are dropped and counted
    (stale live telemetry has no replay value). Link transitions are logged
    once per state change, never per dropped result. `close` blocks for up
    to `connect_timeout + 1.0` seconds so an in-flight connect attempt can
    finish and be discarded cleanly.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        connect_timeout: float = 5.0,
        reconnect_initial_delay_s: float = 0.5,
        reconnect_backoff_multiplier: float = 2.0,
        reconnect_max_delay_s: float = 15.0,
        reconnect_jitter_s: float = 0.1,
    ) -> None:
        if reconnect_initial_delay_s <= 0:
            raise ValueError(
                "reconnect_initial_delay_s must be > 0, "
                f"got {reconnect_initial_delay_s}"
            )
        if reconnect_backoff_multiplier < 1.0:
            raise ValueError(
                "reconnect_backoff_multiplier must be >= 1, "
                f"got {reconnect_backoff_multiplier}"
            )
        if reconnect_max_delay_s < reconnect_initial_delay_s:
            raise ValueError(
                "reconnect_max_delay_s must be >= reconnect_initial_delay_s, "
                f"got {reconnect_max_delay_s}"
            )
        if reconnect_jitter_s < 0:
            raise ValueError(
                f"reconnect_jitter_s must be >= 0, got {reconnect_jitter_s}"
            )
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._initial_delay_s = reconnect_initial_delay_s
        self._backoff_multiplier = reconnect_backoff_multiplier
        self._max_delay_s = reconnect_max_delay_s
        self._jitter_s = reconnect_jitter_s
        self._lock = Lock()
        self._stop_event = Event()
        self._need_connect = Event()
        self._need_connect.set()
        self._sock: socket.socket | None = None
        self._stream: IO[str] | None = None
        self._current_delay_s = reconnect_initial_delay_s
        self._connect_attempts = 0
        self._reconnects = 0
        self._dropped_results = 0
        self._dropped_since_down = 0
        self._last_backoff_s = 0.0
        self._ever_connected = False
        self._down_logged = False
        self._connector = Thread(
            target=self._run_connector, name="tcp-emitter-connector", daemon=True
        )
        self._connector.start()

    def stats(self) -> TCPSocketEmitterStats:
        with self._lock:
            return TCPSocketEmitterStats(
                connected=self._stream is not None,
                connect_attempts=self._connect_attempts,
                reconnects=self._reconnects,
                dropped_results=self._dropped_results,
                last_backoff_s=self._last_backoff_s,
            )

    def emit(self, result: PipelineResult) -> None:
        with self._lock:
            stream = self._stream
            if stream is None:
                self._dropped_results += 1
                self._dropped_since_down += 1
                return
        try:
            stream.write(json.dumps(pipeline_result_to_payload(result)) + "\n")
            stream.flush()
        except (OSError, ValueError):
            self._handle_send_failure(stream)

    def close(self) -> None:
        self._stop_event.set()
        self._need_connect.set()
        self._connector.join(timeout=self._connect_timeout + 1.0)
        with self._lock:
            self._teardown_locked()

    def _run_connector(self) -> None:
        while not self._stop_event.is_set():
            if not self._need_connect.wait(timeout=0.2):
                continue
            if self._stop_event.is_set():
                return
            if self._attempt_connect():
                continue
            if self._stop_event.is_set():
                return
            self._stop_event.wait(self._advance_backoff())

    def _attempt_connect(self) -> bool:
        with self._lock:
            self._connect_attempts += 1
        try:
            sock = socket.create_connection(
                (self._host, self._port), timeout=self._connect_timeout
            )
        except OSError as exc:
            with self._lock:
                should_log = not self._down_logged
                self._down_logged = True
            if should_log:
                logger.warning(
                    "telemetry endpoint %s:%s unreachable (%s); retrying with backoff",
                    self._host,
                    self._port,
                    exc,
                )
            return False
        for level, option in (
            (socket.IPPROTO_TCP, socket.TCP_NODELAY),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE),
        ):
            try:
                sock.setsockopt(level, option, 1)
            except OSError:
                pass
        stream = sock.makefile("w", encoding="utf-8", newline="\n")
        with self._lock:
            if self._stop_event.is_set():
                # close() raced this in-flight attempt: discard the socket
                # instead of repopulating a closed emitter.
                discard = True
            else:
                discard = False
                self._sock = sock
                self._stream = stream
                if self._ever_connected:
                    self._reconnects += 1
                self._ever_connected = True
                self._current_delay_s = self._initial_delay_s
                self._last_backoff_s = 0.0
                dropped_while_down = self._dropped_since_down
                self._dropped_since_down = 0
                self._down_logged = False
                self._need_connect.clear()
        if discard:
            try:
                stream.close()
            except (OSError, ValueError):
                pass
            try:
                sock.close()
            except OSError:
                pass
            return False
        logger.info(
            "telemetry connected to %s:%s (%d results dropped while down)",
            self._host,
            self._port,
            dropped_while_down,
        )
        return True

    def _advance_backoff(self) -> float:
        with self._lock:
            delay = self._current_delay_s
            if self._jitter_s > 0:
                delay += random.uniform(0.0, self._jitter_s)
            self._last_backoff_s = delay
            self._current_delay_s = min(
                self._current_delay_s * self._backoff_multiplier, self._max_delay_s
            )
            return delay

    def _handle_send_failure(self, stream: IO[str]) -> None:
        with self._lock:
            self._dropped_results += 1
            self._dropped_since_down += 1
            lost_current = self._stream is stream
            if lost_current:
                self._teardown_locked()
                self._down_logged = True
                self._need_connect.set()
        if lost_current:
            logger.warning(
                "telemetry connection to %s:%s lost", self._host, self._port
            )

    def _teardown_locked(self) -> None:
        stream, sock = self._stream, self._sock
        self._stream = None
        self._sock = None
        if stream is not None:
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class LiveDashboardEmitter:
    """Full-screen rich dashboard, refreshes in place. Use as a context manager.

    Example:
        with LiveDashboardEmitter() as dash:
            for frame in source:
                result = pipeline.feed(frame)
                if result is not None:
                    dash.emit(result)
    """

    def __init__(self, *, history_size: int = 40, refresh_per_second: int = 4) -> None:
        from rich.console import Console
        from rich.live import Live

        self._console = Console()
        self._latest: Optional[PipelineResult] = None
        self._motion_history: deque[float] = deque(maxlen=history_size)
        self._breath_history: deque[float] = deque(maxlen=history_size)
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=refresh_per_second,
            screen=False,
        )

    def __enter__(self) -> "LiveDashboardEmitter":
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._live.__exit__(exc_type, exc, tb)

    def emit(self, result: PipelineResult) -> None:
        self._latest = result
        if result.motion is not None:
            self._motion_history.append(result.motion.motion_score)
        if result.breath_rate is not None:
            self._breath_history.append(result.breath_rate.rate_bpm)
        self._live.update(self._render())

    def close(self) -> None:
        pass

    def _render(self):
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        if self._latest is None:
            return Panel(
                Text("warming up — waiting for first window...", style="dim"),
                title="wifi-sensing-edge",
                border_style="cyan",
            )

        t = self._latest.timestamp_us / 1_000_000.0
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(justify="left", style="bold", no_wrap=True)
        table.add_column(justify="left")

        breath = self._latest.breath_rate
        if breath is not None:
            bpm_text = Text()
            bpm_text.append(f"{breath.rate_bpm:5.1f}", style="bold cyan")
            bpm_text.append(" bpm", style="dim")
            table.add_row("breath rate", bpm_text)
            conf_color = "green" if breath.confidence >= 100 else "yellow"
            conf_text = Text(f"{breath.confidence:8.0f}x", style=conf_color)
            table.add_row("  confidence", conf_text)
            spark = _sparkline(list(self._breath_history))
            table.add_row("  history", Text(spark, style="cyan"))
        else:
            table.add_row("breath rate", Text("warming up", style="dim"))

        table.add_row("", "")

        motion = self._latest.motion
        if motion is not None:
            color = {
                "idle": "blue",
                "presence": "green",
                "movement": "yellow",
            }.get(motion.state.value, "white")
            state_text = Text(motion.state.value.upper(), style=f"bold {color}")
            table.add_row("motion", state_text)
            table.add_row("  score", f"{motion.motion_score:8.2f}")
            spark = _sparkline(list(self._motion_history))
            table.add_row("  history", Text(spark, style=color))
        else:
            table.add_row("motion", Text("warming up", style="dim"))

        return Panel(
            table,
            title=f"wifi-sensing-edge  ·  t={t:.1f}s",
            border_style="cyan",
            padding=(1, 2),
        )


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    ticks = " ▁▂▃▄▅▆▇█"
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-9:
        return ticks[1] * len(values)
    span = hi - lo
    out = []
    for v in values:
        norm = (v - lo) / span
        idx = 1 + int(norm * (len(ticks) - 2))
        out.append(ticks[idx])
    return "".join(out)
