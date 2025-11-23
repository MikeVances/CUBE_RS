#!/usr/bin/env python3
"""Manual probe for ESQ-230 problematic registers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modbus.universal_reader import UniversalModbusReader  # noqa: E402
from core.device_adapters.base import RegisterType  # noqa: E402

# Значения в документации указаны как «только чтение», но на реальном ESQ-230
# тесты показывают, что регистры читаются только через FC03 (holding).
# Скрипт оставляем универсальным, но теперь он по умолчанию не шлёт FC04,
# чтобы не пугать пользователя ошибками.
DEFAULT_RANGES: List[Tuple[int, int]] = [
    (0x1001, 8),  # set freq .. running speed
    (0x1009, 4),  # IO status + AI voltage
    (0x1015, 8),  # remaining run .. running time
]


def read_block(reader: UniversalModbusReader, slave: int, start: int, count: int, reg_type: RegisterType) -> None:
    proto = "FC04" if reg_type == RegisterType.INPUT else "FC03"
    try:
        request = reader._build_modbus_request(slave, start, count=count, register_type=reg_type)
        reader.serial_connection.write(request)
        response_len = 5 + count * 2
        response = reader.serial_connection.read(response_len)
        values = reader._parse_modbus_response(response, expected_count=count)
        if values is None:
            print(f"  {proto} 0x{start:04X} len={count}: ❌ ошибка/нет ответа")
            return
        print(f"  {proto} 0x{start:04X} len={count}: {values}")
    except Exception as exc:
        print(f"  {proto} 0x{start:04X} len={count}: ❌ {exc}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Probe ESQ-230 registers with FC03/FC04")
    parser.add_argument("--port", required=True)
    parser.add_argument("--slave", type=int, required=True)
    parser.add_argument("--ranges", help="Custom ranges start:count,... in hex", default=None)
    parser.add_argument(
        "--fc04",
        action="store_true",
        help="Дополнительно попробовать FC04 (по умолчанию только FC03)",
    )
    args = parser.parse_args(argv)

    ranges = DEFAULT_RANGES
    if args.ranges:
        parsed = []
        for chunk in args.ranges.split(","):
            try:
                start_str, count_str = chunk.split(":")
                parsed.append((int(start_str, 16), int(count_str, 0)))
            except Exception as exc:
                raise SystemExit(f"Invalid range '{chunk}': {exc}")
        ranges = parsed

    reader = UniversalModbusReader(port=args.port, baudrate=9600, timeout=1.0)
    if not reader.connect():
        print("❌ Не удалось подключиться к порту")
        return 1

    try:
        for start, count in ranges:
            print(f"Пробуем диапазон 0x{start:04X} len={count}")
            read_block(reader, args.slave, start, count, RegisterType.HOLDING)
            if args.fc04:
                read_block(reader, args.slave, start, count, RegisterType.INPUT)
    finally:
        reader.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
