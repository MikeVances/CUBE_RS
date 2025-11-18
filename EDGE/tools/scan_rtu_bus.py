#!/usr/bin/env python3
"""
Сканер Modbus RTU шины на одном последовательном порту.

Пробегает по диапазону slave ID и пытается определить тип устройства:
 - VFD‑INVERTER: успешно читается U0‑00 (0x1000) через FC03/FC04
 - KUB‑1063: успешно читается регистр 0x0301 (software_version) через FC03

Пример:
  python EDGE/tools/scan_rtu_bus.py --port /dev/ttys027 --start 1 --end 40

Выводит табличный отчёт и (опционально) JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scan Modbus RTU bus and guess device types")
    p.add_argument("--port", required=True, help="Serial port path (e.g. /dev/ttyS0 or /dev/ttys027)")
    p.add_argument("--baudrate", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stopbits", type=int, default=1)
    p.add_argument("--bytesize", type=int, default=8)
    p.add_argument("--timeout", type=float, default=0.5)
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=32)
    p.add_argument("--json", action="store_true", help="Print JSON instead of table")
    p.add_argument("--verbose", action="store_true")
    return p


@dataclass
class ScanItem:
    slave_id: int
    status: str  # connected/partial/no-response
    device_type: Optional[str] = None
    info: Dict[str, Any] = None  # type: ignore[assignment]
    error: Optional[str] = None


def get_client(port: str, baudrate: int, bytesize: int, parity: str, stopbits: int, timeout: float):
    # pymodbus 3.x
    try:
        from pymodbus.client import ModbusSerialClient
        try:
            from pymodbus.framer import FramerType
        except Exception:
            FramerType = None
    except Exception:
        # pymodbus 2.x
        from pymodbus.client.sync import ModbusSerialClient  # type: ignore
        FramerType = None  # type: ignore

    if FramerType is not None:
        return ModbusSerialClient(
            port=port,
            framer=FramerType.RTU,  # type: ignore[arg-type]
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
        )
    else:
        return ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
        )


def make_reader(client):
    import inspect

    fn_h = getattr(client, "read_holding_registers")
    fn_i = getattr(client, "read_input_registers")
    sig_h = inspect.signature(fn_h)
    sig_i = inspect.signature(fn_i)
    kw_h = "slave" if "slave" in sig_h.parameters else ("unit" if "unit" in sig_h.parameters else None)
    kw_i = "slave" if "slave" in sig_i.parameters else ("unit" if "unit" in sig_i.parameters else None)

    def read(kind: str, address: int, count: int, slave_id: int):
        if kind == "holding":
            kwargs = {kw_h: slave_id} if kw_h else {}
            return fn_h(address, count, **kwargs)
        else:
            kwargs = {kw_i: slave_id} if kw_i else {}
            return fn_i(address, count, **kwargs)

    return read


DEVICE_PROBES = [
    (
        "VFD-INVERTER",
        [
            {"kind": "holding", "address": 0x1000, "require_non_zero": True},
            {"kind": "input", "address": 0x1000, "require_non_zero": True},
        ],
    ),
    (
        "KUB-1112",
        [
            {"kind": "holding", "address": 0x0405, "require_non_zero": True},
            {"kind": "holding", "address": 0x0400, "require_non_zero": False},
        ],
    ),
    (
        "KUB-1063",
        [
            {"kind": "holding", "address": 0x160E, "expected_value": 1},
            {"kind": "holding", "address": 0x0301, "require_non_zero": True},
        ],
    ),
]


def detect_device_type(read, slave_id: int, verbose: bool = False) -> tuple[str | None, dict[str, Any] | None]:
    for device_type, probes in DEVICE_PROBES:
        requires_positive = any(
            probe.get("require_non_zero") or probe.get("expected_value") is not None for probe in probes
        )
        positive_info: dict[str, Any] | None = None
        fallback_info: dict[str, Any] | None = None
        for probe in probes:
            try:
                r = read(
                    probe.get("kind", "holding"),
                    probe["address"],
                    probe.get("count", 1),
                    slave_id,
                )
                if not hasattr(r, "isError") or r.isError() or not getattr(r, "registers", None):
                    continue
                registers = getattr(r, "registers", [])
                expected_value = probe.get("expected_value")
                positive_probe = probe.get("require_non_zero") or expected_value is not None
                if expected_value is not None:
                    if not registers or registers[0] != expected_value:
                        continue
                if probe.get("require_non_zero"):
                    if not any(val not in (0, None) for val in registers):
                        continue
                info = {
                    "address": f"0x{probe['address']:04X}",
                    "fn": probe.get("kind", "holding"),
                    "value": registers[0] if registers else None,
                }
                if positive_probe:
                    positive_info = info
                    break
                fallback_info = info
            except Exception as exc:
                if verbose:
                    print(f"ID {slave_id}: {device_type} probe err: {exc}")
                continue
        if positive_info:
            return device_type, positive_info
        if not requires_positive and fallback_info:
            return device_type, fallback_info
    return None, None


def classify_device(read, slave_id: int, verbose: bool = False) -> ScanItem:
    dev_type, info = detect_device_type(read, slave_id, verbose=verbose)
    if dev_type:
        return ScanItem(slave_id, "connected", dev_type, info)
    return ScanItem(slave_id, "no-response")


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    client = get_client(
        args.port,
        args.baudrate,
        args.bytesize,
        args.parity,
        args.stopbits,
        args.timeout,
    )
    if not client.connect():
        print(f"❌ Не удалось подключиться к {args.port}")
        return 2

    try:
        read = make_reader(client)
        results: list[ScanItem] = []
        for sid in range(args.start, args.end + 1):
            item = classify_device(read, sid, args.verbose)
            results.append(item)
    finally:
        client.close()

    if args.json:
        payload = [
            {
                "slave_id": it.slave_id,
                "status": it.status,
                "device_type": it.device_type,
                "info": it.info or {},
                "error": it.error,
            }
            for it in results
        ]
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print("\nСкан шины:")
    print("=" * 60)
    ok = 0
    for it in results:
        if it.status == "connected":
            ok += 1
            line = f"ID {it.slave_id:>3}: {it.device_type}"
            if it.device_type == "VFD-INVERTER" and it.info:
                fn = it.info.get("fn")
                line += f" (read:{fn})"
            print(line)
        else:
            print(f"ID {it.slave_id:>3}: no-response")
    print("-" * 60)
    print(f"Найдено устройств: {ok} из {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
