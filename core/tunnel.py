"""Quản lý Cloudflare Quick Tunnel cho dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import signal
from pathlib import Path
from typing import Any

from core.logger import app_logger

DEFAULT_BINARY_PATH = "/usr/local/bin/cloudflared"
URL_TIMEOUT_SECONDS = 25.0
TERMINATE_TIMEOUT_SECONDS = 5.0
URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class CloudflareTunnelManager:
    """Chạy cloudflared quick tunnel và theo dõi trạng thái cho API."""

    def __init__(self, binary_path: str = DEFAULT_BINARY_PATH) -> None:
        self.binary_path: str = binary_path
        self.process: asyncio.subprocess.Process | None = None
        self.public_url: str | None = None
        self.is_running: bool = False
        self._drain_task: asyncio.Task[None] | None = None
        self._unavailable_warned: bool = False

    def is_available(self) -> bool:
        """Kiểm tra binary cloudflared tồn tại và có thể thực thi."""
        path = Path(self.binary_path)
        if path.is_file() and os.access(path, os.X_OK):
            self._unavailable_warned = False
            return True

        # Fallback: tìm cloudflared trong PATH
        found = shutil.which("cloudflared")
        if found is not None:
            if found != self.binary_path:
                app_logger.info("Dùng cloudflared từ PATH: %s", found)
            self.binary_path = found
            self._unavailable_warned = False
            return True

        if not self._unavailable_warned:
            app_logger.error(
                "Không tìm thấy cloudflared (đã kiểm tra %s và PATH).",
                self.binary_path,
            )
            self._unavailable_warned = True
        return False

    async def start(self, local_port: int) -> str | None:
        """Chạy quick tunnel tới ``127.0.0.1:{local_port}``, trả public URL."""
        if self.is_running:
            app_logger.info("Tunnel đang chạy; dừng tunnel cũ trước khi tạo mới.")
            await self.stop()

        if not self.is_available():
            return None

        command = [
            self.binary_path,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{local_port}",
        ]
        app_logger.info("Khởi động cloudflared: %s", " ".join(command))

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as exc:
            app_logger.error("Không chạy được cloudflared: %s", exc)
            return None

        self.process = process
        self.is_running = True

        url = await self._wait_for_url(process)
        if url is None:
            await self.stop()
            return None

        self.public_url = url
        # Đọc tiếp output còn lại để tránh đầy buffer ống
        self._drain_task = asyncio.create_task(
            self._drain_output(process), name="cloudflared-output-drain"
        )
        app_logger.info("Tunnel công khai: %s", url)
        return url

    async def _wait_for_url(self, process: asyncio.subprocess.Process) -> str | None:
        """Đọc output cloudflared tới khi tìm thấy URL hoặc hết thời gian."""
        stream = process.stdout
        if stream is None:
            return None

        loop = asyncio.get_running_loop()
        deadline = loop.time() + URL_TIMEOUT_SECONDS

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                app_logger.error(
                    "Hết thời gian %.0fs chờ cloudflared tạo tunnel.",
                    URL_TIMEOUT_SECONDS,
                )
                return None

            try:
                line = await asyncio.wait_for(stream.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                app_logger.error(
                    "Hết thời gian %.0fs chờ cloudflared tạo tunnel.",
                    URL_TIMEOUT_SECONDS,
                )
                return None

            if not line:
                app_logger.error("cloudflared đã thoát trước khi tunnel sẵn sàng.")
                return None

            text = line.decode("utf-8", errors="replace")
            app_logger.debug("cloudflared: %s", text.rstrip())
            match = URL_PATTERN.search(text)
            if match is not None:
                return match.group(0)

    async def _drain_output(self, process: asyncio.subprocess.Process) -> None:
        """Đọc liên tục output còn lại để tránh đầy buffer ống."""
        stream = process.stdout
        if stream is None:
            return

        try:
            while True:
                line = await stream.readline()
                if not line:
                    return
                app_logger.debug(
                    "cloudflared: %s",
                    line.decode("utf-8", errors="replace").rstrip(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app_logger.debug("Dừng đọc output cloudflared: %s", exc)

    def _signal_process(self, process: asyncio.subprocess.Process, force: bool) -> None:
        """Gửi tín hiệu tới cả process group để dọn cả tiến trình con."""
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError):
            with contextlib.suppress(ProcessLookupError):
                if force:
                    process.kill()
                else:
                    process.terminate()

    async def stop(self) -> None:
        """Dừng cloudflared và dọn toàn bộ trạng thái."""
        if self._drain_task is not None:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task
            self._drain_task = None

        process = self.process
        if process is not None:
            if process.returncode is None:
                self._signal_process(process, force=False)
                try:
                    await asyncio.wait_for(
                        process.wait(), timeout=TERMINATE_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    app_logger.warning(
                        "cloudflared không thoát sau %.0fs; buộc kill.",
                        TERMINATE_TIMEOUT_SECONDS,
                    )
                    self._signal_process(process, force=True)
                    await process.wait()

            # Đọc nốt output để đóng pipe, tránh rò rỉ transport
            stream = process.stdout
            if stream is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(stream.read(), timeout=1.0)

        self.process = None
        self.public_url = None
        self.is_running = False
        app_logger.info("Đã dừng cloudflared tunnel.")

    def get_status(self) -> dict[str, Any]:
        """Trả trạng thái tunnel cho API dashboard."""
        return {
            "available": self.is_available(),
            "running": self.is_running,
            "public_url": self.public_url,
        }


tunnel_manager = CloudflareTunnelManager()

__all__ = ["CloudflareTunnelManager", "tunnel_manager"]
