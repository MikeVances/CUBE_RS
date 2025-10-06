#!/usr/bin/env python3
"""
Unified Telegram Bot launcher (thin wrapper).

Этот модуль сохранён для совместимости со стартовыми скриптами.
Он не содержит собственной реализации бота и просто запускает
полнофункциональный KUBTelegramBot из telegram_bot.bot_main.
"""

import asyncio
import os
import sys

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from core.log_filter import get_secure_logger
except Exception:  # fallback на стандартный logging
    import logging

    def get_secure_logger(name: str):
        return logging.getLogger(name)

from core.config_manager import get_config
from telegram_bot.bot_main import KUBTelegramBot

logger = get_secure_logger(__name__)


async def main():
    cfg = get_config()
    token = cfg.telegram.token
    if not token:
        raise RuntimeError("Не найден TELEGRAM_BОT_TOKEN в конфигурации")

    logger.info("🤖 Запуск единого Telegram бота (KUBTelegramBot)")
    bot = KUBTelegramBot(token)
    await bot.start_bot()


if __name__ == "__main__":
    asyncio.run(main())

