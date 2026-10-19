"""Application configuration and first-run setup."""

from __future__ import annotations

import getpass
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back when invalid."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError:
        logger.warning("Giá trị %s không hợp lệ; dùng mặc định %d", name, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable, falling back when invalid."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning("Giá trị %s không hợp lệ; dùng mặc định %s", name, default)
    return default


def first_run_setup() -> None:
    """Create the local environment file when the application runs initially."""
    if ENV_FILE.exists():
        return

    password = getpass.getpass("Đặt mật khẩu dashboard: ")
    jwt_secret = secrets.token_hex(32)
    ENV_FILE.write_text(
        f"DASHBOARD_PASSWORD={password}\nJWT_SECRET={jwt_secret}\n",
        encoding="utf-8",
    )
    logger.info("Đã tạo file cấu hình môi trường lần đầu tại %s", ENV_FILE)


@dataclass
class AppConfig:
    """Typed application settings loaded from the project environment file."""

    host: str = "0.0.0.0"
    port: int = 8080
    password: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72
    tokens_file: str = "tokens.txt"
    enable_tunnel: bool = True
    cloudflared_path: str = "/usr/local/bin/cloudflared"

    def __post_init__(self) -> None:
        """Load environment values after constructing the configuration."""
        self.reload()

    def reload(self) -> None:
        """Re-read ``.env`` and update all configuration attributes."""
        load_dotenv(dotenv_path=ENV_FILE, override=True)

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = _env_int("PORT", 8080)
        self.password = os.getenv("DASHBOARD_PASSWORD", "")
        self.jwt_secret = os.getenv("JWT_SECRET", "")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expire_hours = _env_int("JWT_EXPIRE_HOURS", 72)
        self.tokens_file = os.getenv("TOKENS_FILE", "tokens.txt")
        self.enable_tunnel = _env_bool("ENABLE_TUNNEL", True)
        self.cloudflared_path = os.getenv(
            "CLOUDFLARED_PATH", "/usr/local/bin/cloudflared"
        )


first_run_setup()
config = AppConfig()
