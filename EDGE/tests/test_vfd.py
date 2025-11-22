#!/usr/bin/env python3
"""Live VFD reader test – polls a real VFD/Inverter using the documented register map."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_registry import DeviceInfo, DeviceType  # noqa: E402
from core.device_adapters.base import (  # noqa: E402
    RegisterInfo,
    RegisterType,
    ValueType,
)
from core.device_adapters.vfd_inverter import VFDInverterAdapter  # noqa: E402
from modbus.universal_reader import UniversalModbusReader  # noqa: E402


ADAPTER = VFDInverterAdapter()
REGISTER_SPECS: Dict[str, RegisterInfo] = ADAPTER.register_map
RUN_STATE_MAP = {1: "Вперёд", 2: "Назад", 3: "Стоп"}


def _parse_value(info: RegisterInfo, raw: int) -> Tuple[object, str]:
    if info.special_values and raw in info.special_values:
        status = info.special_values[raw]
        return status, status

    value = raw
    if info.signed and raw > 0x7FFF:
        value = raw - 0x10000

    if info.value_type == ValueType.VERSION:
        major = value // 100
        minor = value % 100
        return f"{major}.{minor:02d}", "ok"

    if info.value_type == ValueType.BITFIELD:
        return value, "ok"

    if info.value_type in (ValueType.FLOAT, ValueType.PERCENTAGE, ValueType.TEMPERATURE):
        return value * info.scale, "ok"

    return value, "ok"


def _format_special(value, status):
    if status == "ok":
        return value
    return value


def _format_bitfield(value: int, labels: Dict[int, str]) -> str:
    active = [labels[bit] for bit in sorted(labels) if value & (1 << bit)]
    return ", ".join(active) if active else "нет активных"


def read_vfd_raw(reader: UniversalModbusReader, device: DeviceInfo) -> Dict[int, int]:
    return reader._read_registers_with_types(device.slave_id, REGISTER_SPECS)  # type: ignore[attr-defined]


def parse_vfd_registers(raw: Dict[int, int]) -> Dict[str, Tuple[object, str]]:
    parsed: Dict[str, Tuple[object, str]] = {}
    for name, info in REGISTER_SPECS.items():
        if info.address not in raw:
            continue
        parsed[name] = _parse_value(info, raw[info.address])
    return parsed


def describe_fault(code: object) -> str:
    if code in (0, None, "no_fault"):
        return "нет"
    try:
        fault_int = int(code)
    except Exception:
        return str(code)
    desc = ADAPTER.fault_description(fault_int)
    return f"Err{fault_int:02d} – {desc}" if desc else f"Err{fault_int:02d}"


def run_live_vfd(port: str, slave_id: int, timeout: float = 1.0) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    try:
        device = DeviceInfo(
            device_id=slave_id,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=slave_id,
            name=f"LIVE VFD #{slave_id}",
            enabled=True,
        )

        print(f"📡 Читаем VFD (port={port}, slave_id={slave_id})")
        raw = read_vfd_raw(reader, device)
        if not raw:
            print("❌ Данные не получены")
            return False

        parsed = parse_vfd_registers(raw)
        print(f"✅ Получены {len(parsed)} регистров")

        def show(name: str, formatter=lambda v: v):
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {value} ({status})")
            else:
                print(f"   {name}: {formatter(value)}")

        if "running_state" in REGISTER_SPECS:
            show("running_state", lambda v: RUN_STATE_MAP.get(int(v), f"Состояние {v}"))
        if "fault_code" in REGISTER_SPECS:
            show("fault_code", describe_fault)
        if "running_frequency" in REGISTER_SPECS:
            show("running_frequency", lambda v: f"{v:.1f} Hz")
        if "running_speed" in REGISTER_SPECS:
            show("running_speed", lambda v: f"{int(v)} RPM")
        if "dc_bus_voltage" in REGISTER_SPECS:
            show("dc_bus_voltage", lambda v: f"{v:.1f} V")
        if "cumulative_running_time" in REGISTER_SPECS:
            show("cumulative_running_time", lambda v: f"{int(v)} ч")
        if "cumulative_power_consumption" in REGISTER_SPECS:
            show("cumulative_power_consumption", lambda v: f"{v:.1f} кВт·ч")

        if "di_input_state" in REGISTER_SPECS:
            di_value, _ = parsed.get("di_input_state", (None, "missing"))
            if di_value is not None:
                print(f"   di_input_state: 0x{int(di_value):04X}")

        # История аварий и информация недоступны на данной модели

        return True
    finally:
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live VFD reader test (full register map)")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID of VFD")
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args(argv)

    return 0 if run_live_vfd(args.port, args.slave, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
