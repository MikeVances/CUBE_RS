#!/usr/bin/env python3
"""
EDGE Dashboard reader: reads data from SQLite filled by the Gateway.
Based on original dashboard/dashboard_reader.py, adapted to EDGE DB path resolution.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Any, Optional

try:  # pragma: no cover - import path differences in packaging
    from core.config_manager import get_config  # type: ignore
    from core.utils.paths import resolve_under_root  # type: ignore
    from core.device_registry import get_device_registry  # type: ignore
except ImportError:  # pragma: no cover - local fallback when running from EDGE package
    from ..core.config_manager import get_config
    from ..core.utils.paths import resolve_under_root
    from ..core.device_registry import get_device_registry

try:
    _cfg = get_config()
    DB_PATH = resolve_under_root(getattr(_cfg.database, "file", "kub_data.db") or "kub_data.db")
except Exception:
    DB_PATH = resolve_under_root("kub_data.db")

try:
    _devices = get_device_registry().get_all_devices(enabled_only=True)
    DEFAULT_DEVICE_ID = _devices[0].device_id if _devices else 1
except Exception:
    DEFAULT_DEVICE_ID = 1

try:
    from ..core.log_filter import get_secure_logger
    logger = get_secure_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def read_all() -> Optional[dict[str, Any]]:
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM latest_data
                WHERE device_id = ?
                LIMIT 1
                """,
                (DEFAULT_DEVICE_ID,),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning("Нет данных в таблице latest_data")
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
        logger.error(f"Ошибка при чтении данных: {e}")
        return None


def get_historical_data(hours: int = 6) -> Optional[list]:
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    timestamp,
                    temp_inside,
                    temp_target,
                    humidity,
                    co2,
                    nh3,
                    pressure,
                    ventilation_level,
                    software_version
                FROM sensor_data
                WHERE device_id = ? AND timestamp > datetime('now', '-{hours} hours')
                ORDER BY timestamp ASC
                """,
                (DEFAULT_DEVICE_ID,),
            )
            rows = cursor.fetchall()
            if not rows:
                return []
            historical_data = []
            for row in rows:
                data = dict(row)
                try:
                    ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now()
                record = {
                    "timestamp": ts,
                    "temp_inside": data.get("temp_inside"),
                    "temp_target": data.get("temp_target"),
                    "humidity": data.get("humidity"),
                    "co2": data.get("co2"),
                    "nh3": data.get("nh3"),
                    "pressure": data.get("pressure"),
                    "ventilation_level": data.get("ventilation_level"),
                    "software_version": _parse_software_version(
                        data.get("software_version")
                    ),
                }
                historical_data.append(record)
            return historical_data
    except Exception as e:
        logger.error(f"Ошибка исторических данных: {e}")
        return None


def get_statistics() -> Optional[dict[str, Any]]:
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_readings,
                    COUNT(CASE WHEN temp_inside > 0 THEN 1 END) as successful_readings,
                    MAX(updated_at) as last_reading,
                    MIN(updated_at) as first_reading
                FROM latest_data
                WHERE device_id = ? AND updated_at > datetime('now', '-24 hours')
                """,
                (DEFAULT_DEVICE_ID,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            total_readings, successful_readings, last_reading, first_reading = row
            success_rate = (
                (successful_readings / total_readings) if total_readings > 0 else 0
            )
            cursor.execute(
                """
                SELECT COUNT(*) FROM latest_data
                WHERE device_id = ? AND updated_at > datetime('now', '-1 minute')
                """,
                (DEFAULT_DEVICE_ID,),
            )
            recent_readings = cursor.fetchone()[0]
            is_running = recent_readings > 0
            return {
                "success_count": successful_readings,
                "error_count": total_readings - successful_readings,
                "total_readings": total_readings,
                "success_rate": success_rate,
                "is_running": is_running,
                "last_reading": last_reading,
                "first_reading": first_reading,
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
            else:
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
    """Возвращает все доступные регистры (имя, адрес, значение, время)."""
    try:
        from .modbus_storage import read_registers_latest
        from core.config_manager import get_config  # type: ignore

        regs = read_registers_latest()
        meta = get_config().get_modbus_registers_meta()
        # Преобразуем адрес в hex для удобства отображения
        for r in regs:
            try:
                r["address_hex"] = f"0x{int(r['register']) :04X}"
            except Exception:
                r["address_hex"] = ""
            # Признак отображения (если задан в YAML)
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
    print("🧪 Тестирование dashboard_reader (EDGE)…")
    print("DB:", DB_PATH)
    print("Connect:", "OK" if test_connection() else "FAIL")
    print("Read all:", "OK" if read_all() else "NO DATA")
