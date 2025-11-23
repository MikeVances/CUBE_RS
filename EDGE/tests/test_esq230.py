#!/usr/bin/env python3
"""Live ESQ-230 test – polls monitoring registers from actual drive."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_adapters.esq230 import ESQ230Adapter  # noqa: E402
from modbus.universal_reader import UniversalModbusReader  # noqa: E402


ADAPTER = ESQ230Adapter()
REGISTER_SPECS = ADAPTER.register_map


def read_registers(reader: UniversalModbusReader, slave_id: int, batch_size: int) -> Dict[int, int]:
    addresses = [info.address for info in REGISTER_SPECS.values()]
    return reader.read_registers_batch(slave_id, addresses, batch_size=batch_size)


def run_live_esq(port: str, slave_id: int, timeout: float = 0.5, batch_size: int = 8) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    try:
        raw = read_registers(reader, slave_id, batch_size=batch_size)
        if not raw:
            print("❌ Данные не получены")
            return False

        device_data = ADAPTER.parse_device_data(slave_id, raw)
        print(f"✅ Получены данные с {len(device_data.registers)} регистров")
        for name, info in REGISTER_SPECS.items():
            value = device_data.registers.get(name)
            if value is None:
                print(f"   {name}: — (нет ответа)")
                continue
            if name == "status_word":
                raw_val = device_data.raw_registers.get(name, 0)
                print(f"   {name}: {value} (0x{raw_val:04X})")
                continue
            unit = info.unit or ""
            if isinstance(value, float):
                print(f"   {name}: {value:.2f}{unit}")
            else:
                print(f"   {name}: {value}{unit}")

        return True
    finally:
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live ESQ-230 Modbus test")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID of ESQ drive")
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument(
        "--batch",
        type=int,
        default=8,
        help="Максимум регистров за один запрос (default: 8)",
    )
    args = parser.parse_args(argv)
    return 0 if run_live_esq(args.port, args.slave, args.timeout, args.batch) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
