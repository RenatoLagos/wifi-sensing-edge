"""Pipeline result emitters.

An emitter is anything that consumes a `PipelineResult` and surfaces it
somewhere. Three implementations:

  StdoutEmitter         — one human-readable line per result
  JSONLinesEmitter      — one JSON object per result (pipe-friendly)
  LiveDashboardEmitter  — full-screen rich terminal dashboard, in-place
                          updates, includes a motion-score sparkline
"""
from __future__ import annotations

import json
import sys
from collections import deque
from typing import IO, Optional, Protocol

from jetson.pipeline.orchestrator import PipelineResult


class Emitter(Protocol):
    def emit(self, result: PipelineResult) -> None: ...
    def close(self) -> None: ...


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
        payload = {
            "timestamp_us": result.timestamp_us,
            "breath_rate_bpm": (
                result.breath_rate.rate_bpm if result.breath_rate else None
            ),
            "breath_confidence": (
                result.breath_rate.confidence if result.breath_rate else None
            ),
            "motion_state": (
                result.motion.state.value if result.motion else None
            ),
            "motion_score": (
                result.motion.motion_score if result.motion else None
            ),
        }
        self._stream.write(json.dumps(payload) + "\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.flush()


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
