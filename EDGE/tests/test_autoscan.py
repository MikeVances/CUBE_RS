#!/usr/bin/env python3
"""
file: EDGE/tests/test_autoscan.py
description: Тест автосканирования устройств на RS485 шине
author: EDGE Full-Stack RS485 Senior Engineer GPT
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Импортируем функции автосканирования
from start_edge import _autoscan_and_write_config

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Тест автосканирования")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--start", type=int, default=1, help="Start slave ID")
    parser.add_argument("--end", type=int, default=10, help="End slave ID")

    args = parser.parse_args()

    print(f"🔎 Запуск автосканирования {args.port} (slave ID {args.start}-{args.end})")
    print("="*60)

    _autoscan_and_write_config(args.port, args.start, args.end)

    print("="*60)
    print("✅ Автосканирование завершено")

    # Читаем результат
    from pathlib import Path
    config_path = Path(__file__).parent.parent.parent / "config" / "devices.yaml"

    if config_path.exists():
        print(f"\n📄 Результат сохранён в: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("⚠️ Файл devices.yaml не создан")
