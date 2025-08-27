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

def main():
    print("🤖 TELEGRAM BOT - ИЗОЛИРОВАННЫЙ ЗАПУСК")
    print("=" * 40)
    
    # Получаем токен
    try:
        with open("config/bot_secrets.json", 'r') as f:
            secrets = json.load(f)
            token = secrets["telegram"]["bot_token"]
    except Exception as e:
        print(f"❌ Ошибка загрузки токена: {e}")
        return
    
    # Создаем и запускаем бота в изолированном event loop
    bot = KUBTelegramBot(token)
    
    # Принудительно закрываем любые существующие event loops
    try:
        loop = asyncio.get_running_loop()
        loop.close()
    except:
        pass
    
    # Создаем новый event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot.start_bot())
    except KeyboardInterrupt:
        print("\n🛑 Остановка...")
    finally:
        loop.close()

if __name__ == "__main__":
    main()