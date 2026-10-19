"""Tạo và kiểm tra JWT cho dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from config import config
from core.logger import app_logger

# Các path được phép truy cập không cần token
PUBLIC_PATHS: frozenset[str] = frozenset({"/", "/api/login", "/favicon.ico"})


def create_token(subject: str = "dashboard") -> str:
    """Tạo JWT mới với thời hạn lấy từ cấu hình."""
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(hours=config.jwt_expire_hours)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)
    app_logger.debug("Đã tạo token cho %s (hết hạn sau %sh)", subject, config.jwt_expire_hours)
    return token


def verify_token(token: str) -> dict[str, Any] | None:
    """Giải mã token; trả payload hoặc None nếu token không hợp lệ."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm],
        )
        return payload
    except jwt.PyJWTError as exc:
        app_logger.warning("Token không hợp lệ: %s", exc)
        return None


async def auth_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Chặn request không có JWT hợp lệ (trừ các path công khai)."""
    path = request.url.path
    if request.method == "OPTIONS" or path in PUBLIC_PATHS:
        return await call_next(request)

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    token = header.removeprefix("Bearer ").strip()
    if not token or verify_token(token) is None:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return await call_next(request)


__all__ = ["PUBLIC_PATHS", "auth_middleware", "create_token", "verify_token"]
