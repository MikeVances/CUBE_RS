#!/usr/bin/env python3
"""
Простой запускатель Telegram Bot без конфликтов event loop
"""

import asyncio
import sys
import os

# Добавляем пути
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from telegram_bot.bot_main import KUBTelegramBot
import json
import logging

async def run_bot_async():
    """Асинхронная функция для запуска бота"""
    try:
        with open("config/bot_secrets.json", 'r') as f:
            secrets = json.load(f)
            token = secrets["telegram"]["bot_token"]
    except Exception as e:
        print(f"❌ Ошибка загрузки токена: {e}")
        return
    
    bot = KUBTelegramBot(token)
    await bot.start_bot()

def main():
    print("🤖 TELEGRAM BOT - ИЗОЛИРОВАННЫЙ ЗАПУСК")
    print("=" * 40)
    
    try:
        # Проверяем наличие активного event loop
        loop = asyncio.get_running_loop()
        print("⚠️  Обнаружен активный event loop, используем subprocess")
        
        # Запускаем в отдельном процессе
        import subprocess
        import sys
        result = subprocess.run([
            sys.executable, __file__, "--subprocess"
        ], capture_output=False)
        return result.returncode
        
    except RuntimeError:
        # Нет активного loop - можем использовать asyncio.run
        try:
            asyncio.run(run_bot_async())
        except KeyboardInterrupt:
            print("\n🛑 Остановка...")
            return 0

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--subprocess":
        # Запущены в subprocess - используем asyncio.run напрямую  
        asyncio.run(run_bot_async())
    else:
        main()