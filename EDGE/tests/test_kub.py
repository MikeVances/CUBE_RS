#!/usr/bin/env python3
"""Live KUB-1063 reader test – polls a real RTU device via UniversalModbusReader."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_registry import DeviceInfo, DeviceType  # noqa: E402
from modbus.universal_reader import UniversalModbusReader  # noqa: E402


def run_live_kub(port: str, slave_id: int, timeout: float = 0.5) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    device = DeviceInfo(
        device_id=slave_id,
        device_type=DeviceType.KUB_1063,
        slave_id=slave_id,
        name=f"LIVE KUB #{slave_id}",
        enabled=True,
    )

    print(f"📡 Читаем KUB-1063 (port={port}, slave_id={slave_id})")
    data = reader.read_device(device)
    reader.disconnect()

    if not data:
        print("❌ Данные не получены")
        return False

    regs = data.get("registers", {})
    print("✅ Статус:", data.get("connection_status"))
    print("   temp_inside:", regs.get("temp_inside"))
    print("   humidity:", regs.get("humidity"))
    print("   pressure:", regs.get("pressure"))
    print("   grv_base:", regs.get("grv_base"))
    print("   ventilation_level:", regs.get("ventilation_level"))
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live KUB-1063 reader test")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID of KUB")
    parser.add_argument("--timeout", type=float, default=0.5)
    args = parser.parse_args(argv)

    return 0 if run_live_kub(args.port, args.slave, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
