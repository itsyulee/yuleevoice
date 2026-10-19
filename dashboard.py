"""Entrypoint khởi động dashboard (thay thế self-bot.py)."""

from __future__ import annotations

import asyncio
import os
import json
import socket
import sys
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import config, first_run_setup
from core.api import router as api_router, StartBody, VOICE_SETTINGS_FILE
from core.auth import auth_middleware
from core.engine import bot_manager
from core.logger import app_logger, log_handler
from core.tunnel import tunnel_manager
from core.web import dashboard_route, websocket_endpoint

BANNER = """
 ███╗   ███╗ ██████╗ ██╗
 ████╗ ████║██╔════╝ ██║
 ██╔████╔██║██║  ███╗██║
 ██║╚██╔╝██║██║   ██║██║
 ██║ ╚═╝ ██║╚██████╔╝███████╗
 ╚═╝     ╚═╝ ╚═════╝ ╚══════╝ 
"""


def get_local_ip() -> str:
    """Trả về LAN IP của máy (không phải loopback)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Không gửi dữ liệu thật; chỉ để OS chọn interface và IP nguồn
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


_shutdown_done = False


async def shutdown() -> None:
    """Dừng bot và tunnel; chỉ chạy cleanup một lần duy nhất."""
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True

    await bot_manager.stop_all()
    await tunnel_manager.stop()
    print("Hệ thống đã dừng.")
    sys.stdout.flush()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Cleanup khi uvicorn shutdown (Ctrl+C hoặc SIGTERM)."""
    startup_task = None
    if VOICE_SETTINGS_FILE.exists():
        try:
            saved = StartBody(**json.loads(VOICE_SETTINGS_FILE.read_text(encoding="utf-8")))
            channel_ids = [int(cid) for cid in saved.channel_ids]
            if not channel_ids:
                raise ValueError("Danh sách channel trống")
            bot_manager.channel_ids = channel_ids
            if saved.mode == "normal":
                startup_task = asyncio.create_task(
                    bot_manager.start_normal(channel_ids, saved.delay)
                )
            else:
                startup_task = asyncio.create_task(
                    bot_manager.start_auto_room(channel_ids[0], saved.leader_count, saved.delay)
                )
            app_logger.info("Tự động join các channel đã lưu khi khởi động.")
        except (OSError, ValueError, TypeError):
            app_logger.exception("Không đọc được cấu hình voice; hãy nhập lại trên dashboard.")
    try:
        yield
    finally:
        if startup_task is not None:
            startup_task.cancel()
            with suppress(asyncio.CancelledError):
                await startup_task
        await shutdown()


def create_app() -> FastAPI:
    """Tạo FastAPI app với middleware và toàn bộ route."""
    app = FastAPI(title="YuleeVoice", lifespan=lifespan)
    app.middleware("http")(auth_middleware)
    app.include_router(api_router)
    app.add_api_websocket_route("/ws", websocket_endpoint)
    app.add_api_route(
        "/", dashboard_route, methods=["GET"], response_class=HTMLResponse
    )
    return app


def print_banner(lan_ip: str, tunnel_url: str | None) -> None:
    """In banner và link truy cập ra terminal."""
    os.system("cls" if os.name == "nt" else "clear")
    print(BANNER)
    print()
    print(" Dashboard đang chạy!")
    print()
    print(f" Truy cập LAN   : http://{lan_ip}:{config.port}")
    if tunnel_url:
        print(f" Truy cập Remote: {tunnel_url}")
    else:
        print(" Cloudflare Tunnel không khả dụng")
    print()
    print(" Bấm Ctrl+C để dừng hệ thống.")
    # Đảm bảo banner hiện ngay cả khi stdout bị redirect
    sys.stdout.flush()


async def main() -> None:
    """Khởi động dashboard: config, tunnel, web server và cleanup khi dừng."""
    first_run_setup()
    config.reload()

    # Nạp token từ file để giữ nguyên dữ liệu giữa các phiên
    bot_manager.tokens_file = config.tokens_file
    bot_manager.load_tokens()

    loop = asyncio.get_running_loop()
    log_handler.set_loop(loop)

    app = create_app()
    lan_ip = get_local_ip()

    try:
        tunnel_url: str | None = None
        if config.enable_tunnel:
            tunnel_url = await tunnel_manager.start(config.port)
            if tunnel_url is None:
                app_logger.warning("Không khởi động được Cloudflare Tunnel.")
        else:
            app_logger.info("Cloudflare Tunnel đang tắt trong cấu hình.")

        print_banner(lan_ip, tunnel_url)

        # uvicorn.run() sẽ tạo event loop mới, không gọi được trong async main;
        # dùng Server.serve() để chạy cùng loop với bot_manager/tunnel.
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.host,
                port=config.port,
                log_level="warning",
            )
        )
        await server.serve()
    finally:
        # Lưới an toàn nếu uvicorn thoát mà không chạy lifespan shutdown
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C rơi ra ngoài main (ví dụ ngay lúc khởi động) -> thoát êm
        pass
