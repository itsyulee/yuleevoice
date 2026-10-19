"""Shim tương thích: mọi thành phần chính nằm trong ``core.engine``.

Module này được giữ lại để các import cũ ``from core.bot import ...``
tiếp tục hoạt động.
"""

from core.engine import Bot, BotManager, BotState, StateListener, bot_manager

__all__ = ["Bot", "BotManager", "BotState", "StateListener", "bot_manager"]
