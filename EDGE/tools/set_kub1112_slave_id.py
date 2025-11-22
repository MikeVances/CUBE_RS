#!/usr/bin/env python3
"""Utility to change Modbus slave ID of a KUB-1112 controller via RS485."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modbus.universal_reader import UniversalModbusReader, RegisterType  # noqa: E402

REGISTER_ADDRESS = 0x0220


def change_slave_id(port: str, current_id: int, new_id: int, baudrate: int = 9600, timeout: float = 1.0) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=baudrate, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось открыть порт {port}")
        return False

    try:
        print(f"📡 Подключаемся к КУБ-1112 (port={port}, slave_id={current_id})")
        print(f"📝 Записываем новый адрес {new_id} в регистр 0x{REGISTER_ADDRESS:04X} (FC06)")
        if not reader.write_single_register(current_id, REGISTER_ADDRESS, new_id):
            print("❌ Запись адреса не удалась")
            return False
    finally:
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")

    # Дадим устройству время применить настройки и переподключимся
    time.sleep(0.5)

    verifier = UniversalModbusReader(port=port, baudrate=baudrate, timeout=timeout)
    if not verifier.connect():
        print("⚠️ Не удалось переподключиться для проверки")
        return False

    try:
        print("✅ Адрес записан, проверяем устройство на новом ID…")
        raw = verifier.read_register(new_id, REGISTER_ADDRESS, register_type=RegisterType.HOLDING)
        if raw is None:
            print("⚠️ Не удалось прочитать подтверждение с нового адреса")
            return False

        if raw != new_id:
            print(f"⚠️ Прочитано значение {raw}, ожидался {new_id}")
            return False

        print(f"🎉 Устройство теперь отвечает на адрес {new_id}")
        return True
    finally:
        verifier.disconnect()
        print(f"🔌 Порт {port} закрыт после проверки")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Change Modbus slave ID of KUB-1112")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0")
    parser.add_argument("--current", type=int, required=True, help="Current slave ID")
    parser.add_argument("--new", dest="new_id", type=int, required=True, help="New slave ID (1-247)")
    parser.add_argument("--baud", type=int, default=9600, help="Baudrate (default 9600)")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial timeout seconds")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not (1 <= args.new_id <= 247):
        print("❌ Новый адрес должен быть в диапазоне 1-247")
        return 1
    if change_slave_id(args.port, args.current, args.new_id, args.baud, args.timeout):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
