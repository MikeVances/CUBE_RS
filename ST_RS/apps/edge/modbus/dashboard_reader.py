#!/usr/bin/env python3
"""
EDGE Dashboard reader: чтение данных из SQLite, заполняемой Gateway
и предоставление полного списка регистров для отладки.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# Определяем путь к БД
def _resolve_db_path() -> str:
    try:
        from core.config_manager import get_config  # type: ignore

        cfg = get_config()
        db_file = getattr(cfg.database, "file", None) or "kub_data.db"
        from core.utils.paths import resolve_under_root
        return resolve_under_root(db_file)
    except Exception:
        from core.utils.paths import resolve_under_root
        return resolve_under_root("data/kub_data.db")


DB_PATH = _resolve_db_path()


def read_all() -> Optional[dict[str, Any]]:
    """Читает актуальные данные из latest_data (id=1)."""
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM latest_data WHERE id = 1 LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                logger.warning("Нет данных в latest_data")
                return None

            data = dict(row)
            data["timestamp"] = datetime.now()

            result = {
                "temp_inside": data.get("temp_inside"),
                "temp_target": data.get("temp_target"),
                "humidity": data.get("humidity"),
                "co2": data.get("co2"),
                "nh3": data.get("nh3"),
                "pressure": data.get("pressure"),
                "ventilation_level": data.get("ventilation_level"),
                "ventilation_target": data.get("ventilation_target"),
                "active_alarms": data.get("active_alarms") or 0,
                "active_warnings": data.get("active_warnings") or 0,
                "digital_outputs_1": data.get("digital_outputs_1"),
                "digital_outputs_2": data.get("digital_outputs_2"),
                "digital_outputs_3": data.get("digital_outputs_3"),
                "pressure_status": data.get("pressure_status"),
                "humidity_status": data.get("humidity_status"),
                "co2_status": data.get("co2_status"),
                "nh3_status": data.get("nh3_status"),
                "device_uid_hi": data.get("device_uid_hi"),
                "device_uid_lo": data.get("device_uid_lo"),
                "device_uid": data.get("device_uid"),
                "software_version": _parse_software_version(
                    data.get("software_version", 0)
                ),
                "timestamp": data["timestamp"],
                "updated_at": data.get("updated_at", datetime.now().isoformat()),
            }
            return result
    except Exception as e:
        logger.error(f"Ошибка чтения latest_data: {e}")
        return None


def get_historical_data(hours: int = 6) -> Optional[list[dict[str, Any]]]:
    """Исторические данные за N часов из sensor_data."""
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"""
                SELECT timestamp, temp_inside, temp_target, humidity, co2, nh3,
                       pressure, ventilation_level, software_version
                FROM sensor_data
                WHERE timestamp > datetime('now', '-{hours} hours')
                ORDER BY timestamp ASC
                """
            )
            rows = cur.fetchall()
            if not rows:
                return []

            hist: list[dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                try:
                    ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now()
                hist.append(
                    {
                        "timestamp": ts,
                        "temp_inside": d.get("temp_inside"),
                        "temp_target": d.get("temp_target"),
                        "humidity": d.get("humidity"),
                        "co2": d.get("co2"),
                        "nh3": d.get("nh3"),
                        "pressure": d.get("pressure"),
                        "ventilation_level": d.get("ventilation_level"),
                        "software_version": _parse_software_version(
                            d.get("software_version")
                        ),
                    }
                )
            return hist
    except Exception as e:
        logger.error(f"Ошибка чтения sensor_data: {e}")
        return None


def get_statistics() -> Optional[dict[str, Any]]:
    """Статистика по latest_data за последние 24 часа."""
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            cur = conn.execute(
                """
                SELECT COUNT(*) as total_readings,
                       COUNT(CASE WHEN temp_inside > 0 THEN 1 END) as successful_readings,
                       MAX(updated_at) as last_reading,
                       MIN(updated_at) as first_reading
                FROM latest_data
                WHERE updated_at > datetime('now', '-24 hours')
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            total, success, last, first = row
            success_rate = (success / total) if total else 0

            cur2 = conn.execute(
                "SELECT COUNT(*) FROM latest_data WHERE updated_at > datetime('now', '-1 minute')"
            )
            is_running = cur2.fetchone()[0] > 0

            return {
                "success_count": success,
                "error_count": total - success,
                "total_readings": total,
                "success_rate": success_rate,
                "is_running": is_running,
                "last_reading": last,
                "first_reading": first,
            }
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        return None


def _parse_software_version(version_raw) -> str:
    if not version_raw:
        return "Неизвестно"
    if isinstance(version_raw, str):
        return version_raw
    try:
        if isinstance(version_raw, (int, float)):
            if version_raw == 0:
                return "Неизвестно"
            if isinstance(version_raw, int):
                major = (version_raw >> 8) & 0xFF
                minor = version_raw & 0xFF
                return f"{major}.{minor}"
            return f"{version_raw:.2f}"
        return str(version_raw)
    except Exception as e:
        return f"Ошибка: {e}"


def test_connection() -> bool:
    try:
        with sqlite3.connect(DB_PATH, timeout=2.0) as conn:
            conn.execute("SELECT 1")
            return True
    except Exception:
        return False


def get_all_registers() -> list[dict[str, Any]]:
    """Все доступные регистры из registers_latest + meta (display)."""
    try:
        from .modbus_storage import read_registers_latest
        from core.config_manager import get_config  # type: ignore

        regs = read_registers_latest()
        meta = get_config().get_modbus_registers_meta()

        for r in regs:
            try:
                r["address_hex"] = f"0x{int(r['register']):04X}"
            except Exception:
                r["address_hex"] = ""
            disp = True
            name = r.get("name")
            if name in meta:
                disp = bool(meta[name].get("display", True))
            r["display"] = disp
        return regs
    except Exception as e:
        logger.error(f"Ошибка чтения реестра регистров: {e}")
        return []


if __name__ == "__main__":
    print("🧪 EDGE dashboard_reader test")
    print("DB:", DB_PATH)
    print("Connect:", "OK" if test_connection() else "FAIL")
    print("Read all:", "OK" if read_all() else "NO DATA")
