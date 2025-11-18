#!/usr/bin/env python3
"""CLI-утилита для сканирования Modbus slave ID на RS485 линии."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-token-for-scan")
os.environ.setdefault("TELEGRAM_ENV_OVERRIDE", "true")

EDGE_ROOT = Path(__file__).resolve().parent.parent
if str(EDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(EDGE_ROOT))

from core.config_manager import get_config
from modbus.reader import KUB1063Reader


LOGGER = logging.getLogger("edge.scan")


@dataclass
class ProbeResult:
    slave_id: int
    status: str
    attempts: int
    info: Dict[str, Any]
    error: str | None = None

    def to_serializable(self) -> Dict[str, Any]:
        payload = {
            "slave_id": self.slave_id,
            "status": self.status,
            "attempts": self.attempts,
            "info": self._serialize_info(self.info),
        }
        if self.error:
            payload["error"] = self.error
        return payload

    @staticmethod
    def _serialize_info(info: Dict[str, Any]) -> Dict[str, Any]:
        serialized: Dict[str, Any] = {}
        for key, value in info.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            else:
                serialized[key] = value
        return serialized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan Modbus slave IDs on RS485 bus")
    parser.add_argument("--port", help="Serial port to probe (defaults to config.rs485.port)")
    parser.add_argument("--baudrate", type=int, help="Baudrate (defaults to config.rs485.baudrate)")
    parser.add_argument("--start", type=int, default=1, help="Start slave ID (inclusive)")
    parser.add_argument("--end", type=int, default=16, help="End slave ID (inclusive)")
    parser.add_argument("--retries", type=int, default=2, help="Attempts per slave ID")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between attempts (seconds)")
    parser.add_argument(
        "--max-miss",
        type=int,
        default=5,
        help="Maximum consecutive missing registers before aborting (default: 5)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print JSON with results instead of human readable table"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress INFO logs (only warnings/errors)"
    )
    return parser


def prompt_range(default_start: int, default_end: int) -> tuple[int, int, int | None]:
    skip = os.getenv("EDGE_SCAN_SKIP_COUNT_PROMPT", "false").lower() in {"1", "true", "yes", "on"}
    if skip:
        return default_start, default_end, None

    try:
        raw = input("Введите количество устройств в сети (Enter чтобы пропустить): ").strip()
        if not raw:
            return default_start, default_end, None
        total = int(raw)
        if total <= 0:
            raise ValueError("Количество должно быть положительным")
        end = default_start + total - 1
        return default_start, end, total
    except (ValueError, EOFError) as exc:
        print(f"Некорректное значение ({exc}). Используем переданные аргументы.")
        return default_start, default_end, None


def configure_logging(quite_mode: bool) -> None:
    level = logging.WARNING if quite_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def summarize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "software_version",
        "device_uid",
        "device_number",
        "factory_number",
        "temp_inside",
        "temp_target",
        "ventilation_scheme",
        "success_rate",
    ]
    summary = {key: payload.get(key) for key in keys if key in payload}
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, datetime):
        summary["timestamp"] = timestamp.isoformat()
    return summary


def confirm_scan(auto: bool) -> bool:
    skip = os.getenv("EDGE_SCAN_SKIP_CONFIRM", "false").lower() in {"1", "true", "yes", "on"}
    if auto or skip or not sys.stdin.isatty():
        return True
    try:
        answer = input("Запустить сканирование? [Y/n]: ").strip().lower()
    except EOFError:
        return False
    if not answer:
        return True
    return answer in {"y", "yes", "д", "да"}


def probe_slave(
    port: str,
    baudrate: int,
    slave_id: int,
    retries: int,
    delay: float,
    max_miss: int,
) -> ProbeResult:
    last_error: str | None = None
    for attempt in range(1, retries + 1):
        LOGGER.debug("Probing slave_id=%s (attempt %s/%s)", slave_id, attempt, retries)
        reader = KUB1063Reader(port=port, baudrate=baudrate, slave_id=slave_id)
        try:
            data = reader.read_all(max_failures=max_miss)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            LOGGER.debug("Read attempt failed: %s", last_error, exc_info=True)
            time.sleep(delay)
            continue

        if not data:
            last_error = "no response"
            time.sleep(delay)
            continue

        status = data.get("connection_status", "unknown")
        if status in {"connected", "partial"}:
            info = summarize_payload(data)
            LOGGER.info(
                "✅ slave_id=%s detected (SW=%s, UID=%s)",
                slave_id,
                info.get("software_version"),
                info.get("device_uid"),
            )
            state = "connected" if status == "connected" else "partial"
            return ProbeResult(slave_id, state, attempt, info)

        last_error = data.get("error") or status
        time.sleep(delay)

    LOGGER.info("❌ slave_id=%s not responding (%s)", slave_id, last_error or "unknown")
    return ProbeResult(slave_id, "no-response", retries, {}, last_error)


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.quiet)

    auto = os.getenv("EDGE_SCAN_AUTO_CONFIRM", "false").lower() in {"1", "true", "yes", "on"}
    if not confirm_scan(auto):
        LOGGER.info("Сканирование отменено пользователем")
        return 0

    start, end, target_count = prompt_range(args.start, args.end)

    if start < 1 or end > 247 or start > end:
        LOGGER.error("Invalid range: start=%s end=%s", start, end)
        return 1

    if args.max_miss < 1:
        LOGGER.warning("max-miss must be >= 1, forcing to 1")
        args.max_miss = 1

    cfg = get_config()
    rs485 = cfg.rs485
    port = args.port or rs485.port
    baudrate = args.baudrate or rs485.baudrate

    LOGGER.info(
        "🔍 Scanning slave IDs %s-%s on port %s (baudrate %s)",
        start,
        end,
        port,
        baudrate,
    )

    results: list[ProbeResult] = []
    try:
        connected_found = 0
        for slave_id in range(start, end + 1):
            result = probe_slave(
                port,
                baudrate,
                slave_id,
                args.retries,
                args.delay,
                args.max_miss,
            )
            results.append(result)
            if result.status == "connected":
                connected_found += 1
            elif result.status == "partial":
                connected_found += 1
            if target_count is not None and connected_found >= target_count:
                LOGGER.info(
                    "✅ Найдено %s из %s ожидаемых устройств, сканирование завершено",
                    connected_found,
                    target_count,
                )
                break
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted by user")
        return 130

    if args.json:
        json.dump([r.to_serializable() for r in results], sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print("\nScan results:")
        print("=" * 60)
        for r in results:
            line = f"ID {r.slave_id:>3}: {r.status}"
            if r.status == "connected":
                info = r.info
                sw = info.get("software_version", "?")
                uid = info.get("device_uid", "?")
                temp = info.get("temp_inside")
                line += f" | SW: {sw} | UID: {uid}"
                if temp is not None:
                    line += f" | Temp: {temp}"
            elif r.status == "partial":
                info = r.info
                sw = info.get("software_version")
                uid = info.get("device_uid")
                details = []
                if sw:
                    details.append(f"SW: {sw}")
                if uid:
                    details.append(f"UID: {uid}")
                if details:
                    line += " | " + ", ".join(details)
            elif r.error:
                line += f" | {r.error}"
            print(line)

        connected = [r for r in results if r.status in {"connected", "partial"}]
        print("-" * 60)
        print(f"Found {len(connected)} device(s) out of {len(results)} scanned")

        if connected:
            cfg = get_config()
            maybe_update_config(cfg.config_dir, connected)

    return 0


def maybe_update_config(config_dir: Path, discovered: list[ProbeResult]) -> None:
    auto_update = os.getenv("EDGE_SCAN_AUTO_UPDATE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    config_path = Path(config_dir) / "devices.yaml"
    devices = load_devices_config(config_path)
    existing_by_slave = {entry.get("slave_id"): entry for entry in devices}
    used_ids = {entry.get("device_id") for entry in devices if entry.get("device_id") is not None}
    next_id = (max(used_ids) if used_ids else 0) + 1

    if not auto_update:
        if not sys.stdin.isatty():
            return
        try:
            answer = input("Обновить config/devices.yaml найденными устройствами? [Y/n]: ").strip().lower()
        except EOFError:
            return
        if answer and answer not in {"y", "yes", "д", "да"}:
            return

    updated = False
    timestamp = datetime.now().isoformat(timespec="seconds")

    for result in discovered:
        slave_id = result.slave_id
        entry = existing_by_slave.get(slave_id)
        info = result.info
        uid = info.get("device_uid")
        name = uid or f"Устройство {slave_id}"

        if entry:
            if entry.get("name") != name:
                entry["name"] = name
                updated = True
            if entry.get("device_type") is None:
                entry["device_type"] = "KUB-1063"
                updated = True
            continue

        while next_id in used_ids:
            next_id += 1

        new_entry = {
            "device_id": next_id,
            "device_type": "KUB-1063",
            "slave_id": slave_id,
            "name": name,
            "description": f"Автообнаружено {timestamp}",
            "enabled": True,
            "location": None,
        }

        devices.append(new_entry)
        existing_by_slave[slave_id] = new_entry
        used_ids.add(next_id)
        next_id += 1
        updated = True

    if updated:
        devices.sort(key=lambda d: d.get("slave_id", 0))
        save_devices_config(config_path, devices)
        LOGGER.info("💾 Обновлён config/devices.yaml (%s устройств)", len(devices))


def load_devices_config(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return list(data.get("devices", []))
    except Exception as exc:
        LOGGER.warning("⚠️ Не удалось прочитать %s: %s", path, exc)
        return []


def save_devices_config(path: Path, devices: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"devices": devices}
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
