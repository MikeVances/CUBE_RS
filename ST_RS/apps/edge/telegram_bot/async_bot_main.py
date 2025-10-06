#!/usr/bin/env python3
"""
Unified Telegram Bot launcher with process management.

Единственная точка входа для Telegram бота с управлением процессами
для предотвращения конфликтов экземпляров.
"""

import asyncio
import os
import sys
import psutil
import signal
import time
import hashlib
from pathlib import Path

# Add EDGE root to Python path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.log_filter import get_secure_logger

from core.config_manager import get_config
from apps.edge.telegram_bot.bot_main import KUBTelegramBot

logger = get_secure_logger(__name__)


def kill_existing_bot_processes():
    """Убивает существующие процессы бота для предотвращения конфликтов"""
    current_pid = os.getpid()
    killed_count = 0
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                    
                cmdline = proc.info['cmdline']
                if cmdline and any(
                    'async_bot_main.py' in arg or 
                    'bot_main.py' in arg or 
                    'start.py' in arg and 'telegram' in ' '.join(cmdline)
                    for arg in cmdline
                ):
                    logger.info(f"🔪 Завершение существующего процесса бота PID: {proc.info['pid']}")
                    proc.terminate()
                    killed_count += 1
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        if killed_count > 0:
            logger.info(f"⏳ Ожидание завершения {killed_count} процессов...")
            time.sleep(3)  # Увеличили время ожидания
            
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при завершении процессов: {e}")


async def main() -> int:
    # Завершаем существующие процессы бота
    logger.info("🔍 Проверка существующих процессов бота...")
    kill_existing_bot_processes()
    
    cfg = get_config()
    token = cfg.telegram.token
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден в конфигурации")
        return 1

    # Диагностика источника токена
    env_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    source = "ENV" if env_token and env_token == token else ("ENC" if env_token == "" else "ENC (overridden)")
    
    def _mask(s: str) -> str:
        return (s[:3] + "***" + s[-3:]) if s and len(s) > 6 else ("***" if s else "")
    
    masked = _mask(token)
    digest = hashlib.sha256(token.encode()).hexdigest()[:10]
    
    logger.info(f"🔑 Token source: {source} | token={masked} | sha256[:10]={digest}")
    logger.info(f"🔐 Админов: {len(cfg.telegram.admin_users)} | Env: {cfg.system.environment}")
    logger.info("🤖 Запуск единого Telegram бота (KUBTelegramBot)")
    
    bot = KUBTelegramBot(token)
    try:
        await bot.start_bot()
        return 0
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота пользователем")
        raise SystemExit(0)

