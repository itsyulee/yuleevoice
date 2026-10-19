"""WebSocket log handler that buffers and streams application logs."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections import deque
from datetime import datetime
from typing import Awaitable, Callable

LogEntry = dict[str, str]
LogListener = Callable[[LogEntry], Awaitable[None]]


logger = logging.getLogger(__name__)

# Internal logger used for handler errors. Propagation is disabled to avoid a
# feedback loop through the websocket handler when a listener fails.
_internal_logger = logging.getLogger("DiscordVoice.internal")
_internal_logger.propagate = False


class WebSocketLogHandler(logging.Handler):
    """Buffer log records and forward them to async listeners in realtime."""

    def __init__(self) -> None:
        """Initialize the buffer, listener list and event loop reference."""
        super().__init__()
        self.logs_buffer: deque[LogEntry] = deque(maxlen=500)
        self.listeners: list[LogListener] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the event loop used for threadsafe listener dispatch."""
        self._loop = loop

    def add_listener(self, callback: LogListener) -> None:
        """Register an async callback that receives every new log entry."""
        if callback not in self.listeners:
            self.listeners.append(callback)

    def remove_listener(self, callback: LogListener) -> None:
        """Unregister a previously added async callback."""
        if callback in self.listeners:
            self.listeners.remove(callback)

    def get_recent_logs(self) -> list[LogEntry]:
        """Return a snapshot of the buffered log entries."""
        return list(self.logs_buffer)

    def clear_logs(self) -> None:
        """Remove every buffered log entry."""
        self.logs_buffer.clear()

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record, buffer it and dispatch it to all listeners."""
        try:
            entry: LogEntry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime(
                    "%H:%M:%S"
                ),
                "level": record.levelname,
                "message": self.format(record),
            }
            self.logs_buffer.append(entry)
            self._dispatch(entry)
        except Exception:
            self.handleError(record)

    def _dispatch(self, entry: LogEntry) -> None:
        """Schedule listener coroutines on the stored event loop."""
        loop = self._loop
        if loop is None or loop.is_closed() or not self.listeners:
            return

        for listener in list(self.listeners):
            try:
                future = asyncio.run_coroutine_threadsafe(listener(entry), loop)
            except RuntimeError:
                continue
            future.add_done_callback(self._on_dispatch_done)

    def _on_dispatch_done(self, future: concurrent.futures.Future[None]) -> None:
        """Log listener failures without interrupting the logging thread."""
        try:
            future.result()
        except Exception as exc:
            _internal_logger.error("WebSocket log listener thất bại: %s", exc)


log_handler = WebSocketLogHandler()
log_handler.setFormatter(logging.Formatter("%(message)s"))
app_logger = logging.getLogger("DiscordVoice")


def _configure_root_logger() -> None:
    """Attach the websocket handler and silence noisy third-party loggers."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if log_handler not in root.handlers:
        root.addHandler(log_handler)

    for name in ("discord", "discord.client", "discord.http", "aiohttp", "websockets"):
        logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)


_configure_root_logger()

__all__ = [
    "LogEntry",
    "LogListener",
    "WebSocketLogHandler",
    "app_logger",
    "log_handler",
]
