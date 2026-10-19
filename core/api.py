"""FastAPI router cung cấp REST API cho dashboard."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import config
from core.auth import create_token
from core.engine import bot_manager
from core.logger import app_logger, log_handler
from core.tunnel import tunnel_manager

router: APIRouter = APIRouter(prefix="/api")


# -----------------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------------
class LoginBody(BaseModel):
    """Body cho endpoint đăng nhập."""

    password: str


class StartBody(BaseModel):
    """Body khởi động bot ở chế độ normal hoặc auto_room."""

    mode: Literal["normal", "auto_room"]
    channel_ids: list[str] = Field(default_factory=list)
    delay: float = 5.0
    leader_count: int = 5


class ToggleBody(BaseModel):
    """Body bật/tắt mic, deaf, video hoặc stream cho một hoặc toàn bộ bot."""

    bot_id: str | None = None
    mute: bool | None = None
    deaf: bool | None = None
    video: bool | None = None
    stream: bool | None = None


class RenameBody(BaseModel):
    """Body đổi nickname cho một hoặc toàn bộ bot."""

    bot_id: str | None = None
    name: str


class MoveBody(BaseModel):
    """Body di chuyển bot tới voice channel khác."""

    target_channel_id: str
    bot_ids: list[str] | None = None


class ReactionBody(BaseModel):
    """Body thả reaction vào một tin nhắn."""

    channel_id: str
    message_id: str
    emoji: str


class TokensBody(BaseModel):
    """Body cập nhật danh sách token."""

    tokens: list[str]


class ChatSingleBody(BaseModel):
    """Body gửi tin nhắn bằng một bot."""

    bot_id: str
    channel_id: str
    message: str


class ChatAllBody(BaseModel):
    """Body gửi tin nhắn bằng toàn bộ bot ready."""

    channel_id: str
    message: str
    delay: float = 1.0


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _parse_int(value: str, field_name: str) -> int:
    """Đổi chuỗi ID sang int, trả lỗi 400 nếu không hợp lệ."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"{field_name} không hợp lệ: {value}"
        )


def _mask_token(token: str) -> str:
    """Che token để hiển thị an toàn trên dashboard."""
    return f"{token[:6]}..."


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.post("/login", response_model=None)
async def login(body: LoginBody) -> dict[str, Any] | JSONResponse:
    """Kiểm tra mật khẩu và trả JWT cho dashboard."""
    if not config.password or not secrets.compare_digest(body.password, config.password):
        app_logger.warning("Đăng nhập thất bại từ dashboard.")
        return JSONResponse(status_code=401, content={"error": "Sai mật khẩu"})

    token = create_token()
    expires_in = config.jwt_expire_hours * 3600
    app_logger.info("Dashboard đăng nhập thành công.")
    return {"token": token, "expires_in": expires_in}


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Tổng quan trạng thái bot và tunnel."""
    return {**bot_manager.get_summary(), **tunnel_manager.get_status()}


@router.post("/start")
async def start(body: StartBody) -> dict[str, Any]:
    """Khởi động bot ở chế độ normal hoặc auto_room (chạy nền)."""
    channel_ids = [_parse_int(cid, "channel_id") for cid in body.channel_ids]
    if not channel_ids:
        raise HTTPException(status_code=400, detail="Cần ít nhất một channel ID")

    if body.mode == "normal":
        asyncio.create_task(bot_manager.start_normal(channel_ids, body.delay))
        message = (
            f"Đã bắt đầu chế độ normal với {len(channel_ids)} channel"
        )
    else:
        lobby_id = channel_ids[0]
        asyncio.create_task(
            bot_manager.start_auto_room(lobby_id, body.leader_count, body.delay)
        )
        message = (
            f"Đã bắt đầu chế độ auto_room tại lobby {lobby_id} "
            f"với {body.leader_count} leader"
        )

    app_logger.info(message)
    return {"success": True, "message": message}


@router.post("/stop")
async def stop() -> dict[str, Any]:
    """Dừng toàn bộ bot."""
    await bot_manager.stop_all()
    return {"success": True, "message": "Đã dừng tất cả bots"}


@router.post("/toggle")
async def toggle(body: ToggleBody) -> dict[str, Any]:
    """Toggle mic/deaf/video hoặc stream cho một bot hoặc toàn bộ bot."""
    if body.stream is not None:
        if body.bot_id is not None:
            success = await bot_manager.stream_single(body.bot_id, body.stream)
            return {"success": True, "affected": 1 if success else 0}
        affected = await bot_manager.stream_all(body.stream)
        return {"success": True, "affected": affected}

    if body.bot_id is not None:
        success = await bot_manager.toggle_single(
            body.bot_id, mute=body.mute, deaf=body.deaf, video=body.video
        )
        return {"success": True, "affected": 1 if success else 0}

    affected = await bot_manager.toggle_all(
        mute_toggle=bool(body.mute),
        cam_toggle=bool(body.video),
        deaf_toggle=bool(body.deaf),
    )
    return {"success": True, "affected": affected}


@router.post("/rename")
async def rename(body: RenameBody) -> dict[str, Any]:
    """Đổi nickname cho một bot hoặc toàn bộ bot."""
    if body.bot_id is not None:
        success = await bot_manager.rename_single(body.bot_id, body.name)
        return {"success": True, "affected": 1 if success else 0}

    affected = await bot_manager.rename_all(body.name)
    return {"success": True, "affected": affected}


@router.post("/move")
async def move(body: MoveBody) -> dict[str, Any]:
    """Di chuyển bot tới voice channel chỉ định (join ngay và cập nhật state)."""
    target_channel_id = _parse_int(body.target_channel_id, "target_channel_id")
    moved = await bot_manager.move_bots(target_channel_id, body.bot_ids)
    return {"success": True, "moved": moved}


@router.get("/bots/{bot_id}/voice-channels")
async def get_bot_voice_channels(bot_id: str) -> dict[str, Any]:
    """Liệt kê voice/stage channel khả dụng cho một bot."""
    channels = bot_manager.get_available_voice_channels(bot_id)
    return {"channels": channels}


@router.post("/chat/single")
async def chat_single(body: ChatSingleBody) -> dict[str, Any]:
    """Gửi tin nhắn bằng một bot tới text channel chỉ định."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")
    channel_id = _parse_int(body.channel_id, "channel_id")
    sent = await bot_manager.chat_single(body.bot_id, channel_id, message)
    return {"success": True, "sent": 1 if sent else 0}


@router.post("/chat/all")
async def chat_all(body: ChatAllBody) -> dict[str, Any]:
    """Gửi tin nhắn bằng toàn bộ bot ready với delay giữa mỗi bot."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")
    channel_id = _parse_int(body.channel_id, "channel_id")
    delay = max(0.0, body.delay)
    sent = await bot_manager.chat_all(channel_id, message, delay)
    return {"success": True, "sent": sent}


@router.post("/reaction")
async def reaction(body: ReactionBody) -> dict[str, Any]:
    """Cho toàn bộ bot thả reaction vào tin nhắn chỉ định."""
    channel_id = _parse_int(body.channel_id, "channel_id")
    message_id = _parse_int(body.message_id, "message_id")
    reacted = await bot_manager.spam_reaction(channel_id, message_id, body.emoji)
    return {"success": True, "reacted": reacted}


@router.get("/tokens")
async def get_tokens() -> dict[str, Any]:
    """Trả danh sách token kèm bản đã che."""
    tokens = list(bot_manager.tokens)
    return {
        "count": len(tokens),
        "tokens": [
            {"index": index, "masked": _mask_token(token), "full": token}
            for index, token in enumerate(tokens)
        ],
    }


@router.put("/tokens")
async def update_tokens(body: TokensBody) -> dict[str, Any]:
    """Lưu danh sách token mới vào file."""
    bot_manager.save_tokens(body.tokens)
    return {"success": True, "count": len(bot_manager.tokens)}


@router.get("/logs")
async def get_logs() -> dict[str, Any]:
    """Trả các log gần đây đang được buffer."""
    return {"logs": log_handler.get_recent_logs()}


@router.delete("/logs")
async def delete_logs() -> dict[str, Any]:
    """Xoá toàn bộ log đang buffer."""
    log_handler.clear_logs()
    return {"success": True}
