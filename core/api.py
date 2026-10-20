"""FastAPI router cung cấp REST API cho dashboard."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import config, PROJECT_DIR
from core.auth import create_token
from core.engine import bot_manager
from core.logger import app_logger, log_handler
from core.tunnel import tunnel_manager

VOICE_SETTINGS_FILE = PROJECT_DIR / "voice_settings.json"

router: APIRouter = APIRouter(prefix="/api")
start_task: asyncio.Task | None = None
channel_labels: dict[str, str] = {}


# -----------------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------------
class LoginBody(BaseModel):
    """Body cho endpoint đăng nhập."""

    password: str


class StartBody(BaseModel):
    """Body khởi động bot ở chế độ normal hoặc auto_room."""

    mode: Literal["normal", "manual", "auto_room"]
    channel_ids: list[str] = Field(default_factory=list)
    assignments: dict[str, str] = Field(default_factory=dict)
    delay: float = Field(default=5.0, ge=0, allow_inf_nan=False)
    leader_count: int = Field(default=5, ge=1)


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


@router.get("/voice-settings")
async def get_voice_settings() -> dict[str, Any]:
    if not VOICE_SETTINGS_FILE.exists():
        return StartBody(mode="normal").model_dump()
    try:
        return StartBody.model_validate_json(VOICE_SETTINGS_FILE.read_text(encoding="utf-8")).model_dump()
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="Không đọc được cấu hình voice")


@router.put("/voice-settings")
async def save_voice_settings(body: StartBody, apply_now: bool = False) -> dict[str, Any]:
    if any(not cid.isascii() or not cid.isdigit() or not 17 <= len(cid) <= 20 for cid in body.channel_ids):
        raise HTTPException(status_code=400, detail="Channel ID phải gồm 17–20 chữ số")
    if any(not cid.isascii() or not cid.isdigit() or not 17 <= len(cid) <= 20 for cid in body.assignments.values()):
        raise HTTPException(status_code=400, detail="Channel ID không hợp lệ")
    account_keys = {hashlib.sha256(token.encode()).hexdigest() for token in bot_manager.tokens}
    if any(key not in account_keys for key in body.assignments):
        raise HTTPException(status_code=400, detail="Danh sách bot đã thay đổi, hãy tải lại trang")
    channel_ids = list(dict.fromkeys(body.channel_ids))
    # Channel IDs stay strings to preserve Discord snowflake precision.
    settings = {
        "mode": body.mode, "channel_ids": [str(cid) for cid in channel_ids],
        "delay": body.delay, "leader_count": body.leader_count,
        "assignments": body.assignments,
    }
    temporary = VOICE_SETTINGS_FILE.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        temporary.replace(VOICE_SETTINGS_FILE)
    except OSError:
        app_logger.exception("Không lưu được cấu hình voice")
        raise HTTPException(status_code=500, detail="Không lưu được cấu hình voice")

    if apply_now:
        try:
            await apply_saved_voice(body)
        except HTTPException:
            raise
        except Exception:
            app_logger.exception("Đã lưu nhưng không áp dụng được cấu hình voice")
            raise HTTPException(status_code=500, detail="Đã lưu nhưng không áp dụng được. Hãy cập nhật đủ core/api.py, core/engine.py, core/web.py rồi khởi động lại; xem log hosting nếu vẫn lỗi.")
    return {"success": True, "applied": apply_now, **settings}


async def apply_saved_voice(body: StartBody) -> None:
    global start_task
    if start_task and not start_task.done():
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    if body.mode == "auto_room":
        await bot_manager.stop_all()
        if body.channel_ids and bot_manager.tokens:
            bot_manager.active_mode = "auto_room"
            start_task = asyncio.create_task(bot_manager.start_auto_room(
                int(body.channel_ids[0]), body.leader_count, body.delay))
        return
    if body.mode == "manual":
        assignments = {key: int(cid) for key, cid in body.assignments.items()}
    else:
        tokens = list(dict.fromkeys(token for token in bot_manager.tokens if len(token) >= 5))
        channels = list(dict.fromkeys(body.channel_ids))
        assignments = {hashlib.sha256(token.encode()).hexdigest(): int(cid)
                       for token, cid in zip(tokens, channels)}
    bot_manager.active_mode = body.mode if assignments else "idle"
    start_task = asyncio.create_task(bot_manager.apply_assignments(assignments, body.delay, body.mode))


@router.get("/voice-channel-labels")
async def get_voice_channel_labels() -> dict[str, Any]:
    for bot in bot_manager.bots:
        for guild in bot.guilds:
            for channel in [*guild.voice_channels, *guild.stage_channels]:
                channel_labels[str(channel.id)] = f"{channel.name} - {guild.name}"
    return {"labels": channel_labels}


@router.get("/voice-accounts")
async def get_voice_accounts() -> dict[str, Any]:
    return {"accounts": [
        {"key": hashlib.sha256(token.encode()).hexdigest(), "label": f"Bot {i + 1} · {_mask_token(token)}"}
        for i, token in enumerate(bot_manager.tokens)
    ]}


@router.post("/start")
async def start() -> dict[str, Any]:
    """Start only accounts with explicit saved voice assignments."""
    global start_task
    if (start_task and not start_task.done()) or bot_manager.active_mode != "idle":
        raise HTTPException(status_code=409, detail="Bot đang chạy; hãy Stop trước")
    body = StartBody.model_validate(await get_voice_settings())
    if body.mode == "manual":
        current_keys = {hashlib.sha256(token.encode()).hexdigest() for token in bot_manager.tokens}
        assignments = {key: int(cid) for key, cid in body.assignments.items() if key in current_keys}
        if not assignments:
            raise HTTPException(status_code=400, detail="Hãy chọn voice cho từng bot và lưu trước khi Start")
        bot_manager.active_mode = "manual"
        start_task = asyncio.create_task(bot_manager.start_assigned(assignments, body.delay))
    else:
        if not body.channel_ids or not bot_manager.tokens:
            raise HTTPException(status_code=400, detail="Cần thêm channel và token trước khi Start")
        ids = [_parse_int(cid, "channel_id") for cid in body.channel_ids]
        bot_manager.active_mode = body.mode
        if body.mode == "auto_room":
            start_task = asyncio.create_task(bot_manager.start_auto_room(ids[0], body.leader_count, body.delay))
        else:
            start_task = asyncio.create_task(bot_manager.start_normal(ids, body.delay))
    return {"success": True, "message": "Đã khởi động bot"}


@router.post("/stop")
async def stop() -> dict[str, Any]:
    """Dừng toàn bộ bot."""
    global start_task
    if start_task and not start_task.done():
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    start_task = None
    await bot_manager.stop_all()
    return {"success": True, "message": "Đã dừng tất cả bots"}


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str) -> dict[str, Any]:
    """Stop a single bot without touching the other connections."""
    if not await bot_manager.stop_single(bot_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy bot")
    return {"success": True}


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
