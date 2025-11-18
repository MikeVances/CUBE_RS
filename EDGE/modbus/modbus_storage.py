import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import resolve_under_root


def _resolve_db_path() -> str:
    """Resolve SQLite DB path for EDGE deployment.

    Priority:
    1) DATABASE_URL=sqlite:///absolute/or/relative/path.db
    2) core.config_manager database.file (if available)
    3) apps/edge/storage/kub_data.db (repo-local)
    """
    # 1) DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        p = db_url.replace("sqlite:///", "", 1)
        return resolve_under_root(p)

    # 2) core.config_manager (best effort)
    try:
        from core.config_manager import get_config  # type: ignore

        cfg = get_config()
        db_file = getattr(cfg.database, "file", None) or "kub_data.db"
        return resolve_under_root(db_file)
    except Exception:
        pass

    # 3) Default to apps/edge/storage/kub_data.db
    return resolve_under_root("data/kub_data.db")


DB_FILE = _resolve_db_path()


def _connect():
    """Create SQLite connection with WAL for safe concurrent access."""
    conn = sqlite3.connect(DB_FILE, timeout=10)  # Увеличен таймаут до 10 сек
    # Enable WAL to reduce writer/reader blocking and improve concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    # Добавляем дополнительные настройки для безопасности
    conn.execute("PRAGMA busy_timeout=5000;")  # 5 секунд ожидания при блокировке
    conn.execute("PRAGMA cache_size=-64000;")  # 64MB кэша для производительности
    return conn


_lock = threading.Lock()

# Все регистры из Cube-1063_modbus registers.md (Input Registers)
VFD_FIELDS: list[str] = [
    "running_state",
    "running_frequency",
    "running_speed",
    "output_voltage",
    "output_current",
    "output_power",
    "motor_temperature",
    "igbt_temperature",
    "fault_code",
]

ALL_FIELDS: list[str] = [
    "software_version",  # 0x0301
    "device_uid_hi",  # 0x0302
    "device_uid_lo",  # 0x0303
    "device_uid",      # computed full UID (hex string)
    "digital_outputs_1",  # 0x0081
    "digital_outputs_2",  # 0x0082
    "digital_outputs_3",  # 0x00A2
    "pressure",  # 0x0083
    "pressure_status",  # текстовый статус датчика давления
    "humidity",  # 0x0084
    "humidity_status",  # статус датчика влажности
    "co2",  # 0x0085
    "co2_status",  # статус датчика CO2
    "nh3",  # 0x0086
    "nh3_status",  # статус датчика NH3
    "grv_base",  # 0x0087
    "grv_tunnel",  # 0x0088
    "damper",  # 0x0089
    # 0x008A–0x009B пропущены (групповые)
    "active_alarms",  # 0x00C3
    "registered_alarms",  # 0x00C7
    "active_warnings",  # 0x00CB
    "registered_warnings",  # 0x00CF
    "ventilation_target",  # 0x00D0
    "ventilation_level",  # 0x00D1
    "ventilation_scheme",  # 0x00D2
    "day_counter",  # 0x00D3
    "temp_target",  # 0x00D4
    "temp_inside",  # 0x00D5
    "temp_vent_activation",  # 0x00D6
    # + updated_at
] + VFD_FIELDS

# Поля, представляющие собой битовые маски аварий/предупреждений.
BITMASK_FIELDS = {
    "active_alarms",
    "registered_alarms",
    "active_warnings",
    "registered_warnings",
}


def _normalize_value_for_storage(key: str, value):
    """Преобразует значения перед записью в БД.

    Для битовых масок аварий/предупреждений возвращает hex-представление,
    чтобы избежать переполнения INTEGER и облегчить диагностику.
    Остальные значения возвращаются без изменений.
    """
    if value is None:
        return None

    if key in BITMASK_FIELDS:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            # Если значение уже строка или не приводится к int — сохраняем как есть
            return str(value)

        # Сохраняем как строковое десятичное представление, чтобы избежать переполнения INTEGER
        # и при этом сохранить совместимость с существующим кодом, ожидающим int(int(str_value)).
        return str(int_value)

    return value

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS latest_data (
    device_id INTEGER PRIMARY KEY,
    slave_id INTEGER,
    device_type TEXT,
    connection_status TEXT DEFAULT 'unknown',
    last_error TEXT,
    software_version TEXT,
    device_uid_hi INTEGER,
    device_uid_lo INTEGER,
    device_uid TEXT,
    digital_outputs_1 INTEGER,
    digital_outputs_2 INTEGER,
    digital_outputs_3 INTEGER,
    pressure REAL,
    pressure_status TEXT,
    humidity REAL,
    humidity_status TEXT,
    co2 INTEGER,
    co2_status TEXT,
    nh3 REAL,
    nh3_status TEXT,
    grv_base INTEGER,
    grv_tunnel INTEGER,
    damper INTEGER,
    active_alarms INTEGER,
    registered_alarms INTEGER,
    active_warnings INTEGER,
    registered_warnings INTEGER,
    ventilation_target INTEGER,
    ventilation_level INTEGER,
    ventilation_scheme TEXT,
    day_counter INTEGER,
    temp_target REAL,
    temp_inside REAL,
    temp_vent_activation REAL,
    running_state TEXT,
    running_frequency REAL,
    running_speed REAL,
    output_voltage REAL,
    output_current REAL,
    output_power REAL,
    motor_temperature REAL,
    igbt_temperature REAL,
    fault_code TEXT,
    updated_at TIMESTAMP
);
"""

CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    slave_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    software_version TEXT,
    device_uid_hi INTEGER,
    device_uid_lo INTEGER,
    device_uid TEXT,
    digital_outputs_1 INTEGER,
    digital_outputs_2 INTEGER,
    digital_outputs_3 INTEGER,
    pressure REAL,
    pressure_status TEXT,
    humidity REAL,
    humidity_status TEXT,
    co2 INTEGER,
    co2_status TEXT,
    nh3 REAL,
    nh3_status TEXT,
    grv_base INTEGER,
    grv_tunnel INTEGER,
    damper INTEGER,
    active_alarms INTEGER,
    registered_alarms INTEGER,
    active_warnings INTEGER,
    registered_warnings INTEGER,
    ventilation_target INTEGER,
    ventilation_level INTEGER,
    ventilation_scheme TEXT,
    day_counter INTEGER,
    temp_target REAL,
    temp_inside REAL,
    temp_vent_activation REAL,
    running_state TEXT,
    running_frequency REAL,
    running_speed REAL,
    output_voltage REAL,
    output_current REAL,
    output_power REAL,
    motor_temperature REAL,
    igbt_temperature REAL,
    fault_code TEXT
);
"""

# Key-Value storage for full register catalog (latest snapshot and history)
CREATE_REG_LATEST_SQL = """
CREATE TABLE IF NOT EXISTS registers_latest (
    device_id INTEGER NOT NULL,
    register INTEGER NOT NULL,
    name TEXT,
    value TEXT,
    updated_at TIMESTAMP,
    PRIMARY KEY (device_id, register)
);
"""

CREATE_REG_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS registers_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    register INTEGER,
    name TEXT,
    value TEXT
);
"""

SELECT_SQL_TEMPLATE = f"SELECT {{columns}} FROM latest_data WHERE device_id = ?"


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.row_factory = sqlite3.Row

        _migrate_schema(conn)

        conn.execute(CREATE_SQL)
        conn.execute(CREATE_HISTORY_SQL)
        conn.execute(CREATE_REG_LATEST_SQL)
        conn.execute(CREATE_REG_HISTORY_SQL)
        conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Bring existing single-device schema to multi-device layout."""

    def _table_columns(table: str) -> List[str]:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]

    def _ensure_columns(table: str, columns: Dict[str, str]) -> None:
        if not _table_exists(conn, table):
            return
        existing = set(_table_columns(table))
        for column, col_type in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    # latest_data table migration
    if _table_exists(conn, "latest_data"):
        cols = _table_columns("latest_data")
        if "device_id" not in cols:
            conn.execute("ALTER TABLE latest_data RENAME TO latest_data_legacy")
            conn.execute(CREATE_SQL)

            cur = conn.execute("SELECT * FROM latest_data_legacy")
            for row in cur.fetchall():
                data = dict(row)
                legacy_id = data.get("id", 1)
                snapshot = {
                    key: data.get(key) for key in ALL_FIELDS if key in data
                }
                _insert_or_update_latest(
                    conn,
                    device_id=legacy_id,
                    slave_id=None,
                    device_type=None,
                    connection_status=data.get("connection_status", "unknown"),
                    last_error=data.get("last_error"),
                    payload=snapshot,
                )

            conn.execute("DROP TABLE latest_data_legacy")

    vfd_column_types = {
        "running_state": "TEXT",
        "running_frequency": "REAL",
        "running_speed": "REAL",
        "output_voltage": "REAL",
        "output_current": "REAL",
        "output_power": "REAL",
        "motor_temperature": "REAL",
        "igbt_temperature": "REAL",
        "fault_code": "TEXT",
    }

    _ensure_columns("latest_data", vfd_column_types)

    # sensor_data migration
    if _table_exists(conn, "sensor_data"):
        cols = _table_columns("sensor_data")
        if "device_id" not in cols:
            conn.execute("ALTER TABLE sensor_data ADD COLUMN device_id INTEGER DEFAULT 1")
        if "slave_id" not in cols:
            conn.execute("ALTER TABLE sensor_data ADD COLUMN slave_id INTEGER")

    _ensure_columns("sensor_data", vfd_column_types)

    # registers tables migration
    if _table_exists(conn, "registers_latest"):
        cols = _table_columns("registers_latest")
        if "device_id" not in cols:
            conn.execute("ALTER TABLE registers_latest RENAME TO registers_latest_legacy")
            conn.execute(CREATE_REG_LATEST_SQL)

            cur = conn.execute("SELECT * FROM registers_latest_legacy")
            for row in cur.fetchall():
                conn.execute(
                    """
                    INSERT INTO registers_latest (device_id, register, name, value, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, register) DO UPDATE SET
                        name = excluded.name,
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (1, row["register"], row["name"], row["value"], row["updated_at"]),
                )
            conn.execute("DROP TABLE registers_latest_legacy")

    if _table_exists(conn, "registers_history"):
        cols = _table_columns("registers_history")
        if "device_id" not in cols:
            conn.execute("ALTER TABLE registers_history ADD COLUMN device_id INTEGER DEFAULT 1")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    )
    return cur.fetchone() is not None


def update_data(
    *,
    device_id: int,
    slave_id: Optional[int] = None,
    device_type: Optional[str] = None,
    connection_status: Optional[str] = None,
    last_error: Optional[str] = None,
    **payload: Any,
) -> None:
    """Upsert latest snapshot for a particular device.

    Unknown fields are ignored. Always bumps ``updated_at`` for the device.
    """
    import logging

    if device_id is None:
        raise ValueError("device_id is required for update_data")

    logging.info(
        "🔍 update_data(device_id=%s) с %d параметрами", device_id, len(payload)
    )

    normalized_kwargs: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in ALL_FIELDS:
            normalized_kwargs[key] = _normalize_value_for_storage(key, value)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with _lock, _connect() as conn:
                conn.execute("BEGIN IMMEDIATE;")

                _insert_or_update_latest(
                    conn,
                    device_id=device_id,
                    slave_id=slave_id,
                    device_type=device_type,
                    connection_status=connection_status,
                    last_error=last_error,
                    payload=normalized_kwargs,
                    updated_at=timestamp,
                )

                _append_history_tx(
                    conn,
                    device_id=device_id,
                    slave_id=slave_id,
                    payload=normalized_kwargs,
                    timestamp=timestamp,
                )

                try:
                    _update_registers_snapshot_tx(
                        conn, normalized_kwargs, device_id=device_id, timestamp=timestamp
                    )
                except Exception as exc:  # noqa: BLE001 - логируем и продолжаем
                    logging.warning(f"⚠️ Не удалось обновить KV регистры: {exc}")

                conn.commit()
                logging.info("✅ update_data завершена успешно для device_id=%s", device_id)
                return

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logging.warning(
                    "⚠️ БД заблокирована (попытка %d/%d)", attempt + 1, max_retries
                )
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
        except Exception:
            import logging as _logging
            import traceback

            _logging.error("❌ Ошибка в update_data", exc_info=True)
            _logging.error(traceback.format_exc())
            raise


def _insert_or_update_latest(
    conn: sqlite3.Connection,
    *,
    device_id: int,
    slave_id: Optional[int],
    device_type: Optional[str],
    connection_status: Optional[str],
    last_error: Optional[str],
    payload: Dict[str, Any],
    updated_at: str,
) -> None:
    columns: List[str] = ["device_id", "updated_at"]
    values: List[Any] = [device_id, updated_at]

    def _push(column: str, value: Any) -> None:
        if value is None:
            return
        columns.append(column)
        values.append(value)

    _push("slave_id", slave_id)
    _push("device_type", device_type)
    _push("connection_status", connection_status)
    _push("last_error", last_error)

    for field, value in payload.items():
        columns.append(field)
        values.append(value)

    assignments = ", ".join(f"{col}=excluded.{col}" for col in columns if col != "device_id")
    placeholders = ", ".join("?" for _ in columns)

    sql = (
        f"INSERT INTO latest_data ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(device_id) DO UPDATE SET {assignments}"
    )

    conn.execute(sql, values)


def _append_history_tx(
    conn: sqlite3.Connection,
    *,
    device_id: int,
    slave_id: Optional[int],
    payload: Dict[str, Any],
    timestamp: str,
) -> None:
    if not payload:
        return

    columns: List[str] = ["device_id", "timestamp"]
    values: List[Any] = [device_id, timestamp]

    if slave_id is not None:
        columns.append("slave_id")
        values.append(slave_id)

    for field, value in payload.items():
        columns.append(field)
        values.append(value)

    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO sensor_data ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def _update_registers_snapshot_tx(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    *,
    device_id: int,
    timestamp: str,
):
    """Обновляет таблицу registers_latest и добавляет в registers_history в рамках активной транзакции.

    На вход подаём словарь данных вида name->value. Адреса регистров берём из конфигурации.
    Значения приводим к строке для универсального хранения.
    """
    try:
        # Получаем карту регистров из конфига (name -> addr string)
        from core.config_manager import get_config  # type: ignore

        cfg = get_config()
        if hasattr(cfg, "get_modbus_registers_meta"):
            reg_meta = cfg.get_modbus_registers_meta()
        else:
            reg_meta = {
                name: {"address": address}
                for name, address in cfg.get_all_modbus_registers().items()
            }
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows_latest: List[tuple[Any, ...]] = []
        rows_history: List[tuple[Any, ...]] = []

        for name, meta in reg_meta.items():
            if name not in data:
                continue
            value = data.get(name)
            # Нормализуем адрес
            addr_str = meta.get("address")
            try:
                addr = int(addr_str, 16) if isinstance(addr_str, str) and addr_str.startswith("0x") else int(addr_str)
            except Exception:
                continue
            # Приводим значение к строке для универсального хранения
            val_text = "" if value is None else str(value)
            rows_latest.append((device_id, addr, name, val_text, now))
            rows_history.append((device_id, addr, name, val_text))

        if rows_latest:
            conn.executemany(
                """
                INSERT INTO registers_latest (device_id, register, name, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(device_id, register) DO UPDATE SET
                    name=excluded.name,
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                rows_latest,
            )

        if rows_history:
            conn.executemany(
                "INSERT INTO registers_history (device_id, register, name, value) VALUES (?, ?, ?, ?)",
                rows_history,
            )

    except Exception as e:
        import logging

        logging.warning(f"⚠️ KV обновление регистров пропущено: {e}")


def read_registers_latest(device_id: Optional[int] = None) -> List[dict]:
    """Return latest register snapshot for a device (or the first device)."""
    with _lock, _connect() as conn:
        conn.row_factory = sqlite3.Row
        if device_id is None:
            cur = conn.execute(
                "SELECT device_id, register, name, value, updated_at"
                "  FROM registers_latest ORDER BY device_id, register"
            )
        else:
            cur = conn.execute(
                "SELECT device_id, register, name, value, updated_at"
                "  FROM registers_latest WHERE device_id = ? ORDER BY register",
                (device_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def add_history_record(*, device_id: int, slave_id: Optional[int] = None, **payload: Any) -> None:
    """Public helper to append device history outside update_data."""
    data = {
        key: _normalize_value_for_storage(key, value)
        for key, value in payload.items()
        if key in ALL_FIELDS and value is not None
    }

    if not data:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        _append_history_tx(
            conn,
            device_id=device_id,
            slave_id=slave_id,
            payload=data,
            timestamp=timestamp,
        )
        conn.commit()


def read_data(device_id: Optional[int] = None) -> Dict[str, Any]:
    """Read latest snapshot for a specific device (defaults to first)."""
    columns = ["device_id", "slave_id", "device_type", "connection_status", "last_error"] + ALL_FIELDS + ["updated_at"]
    query_columns = ", ".join(columns)
    sql = SELECT_SQL_TEMPLATE.format(columns=query_columns)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with _lock, _connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if device_id is None:
                    cursor.execute(
                        f"SELECT {query_columns} FROM latest_data ORDER BY device_id LIMIT 1"
                    )
                else:
                    cursor.execute(sql, (device_id,))
                row = cursor.fetchone()
                if not row:
                    return {}
                data = dict(row)
                updated_at = data.get("updated_at")
                if isinstance(updated_at, datetime):
                    data["updated_at"] = updated_at.isoformat()
                return data
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                import logging

                logging.warning(
                    "⚠️ БД заблокирована при чтении, попытка %d/%d",
                    attempt + 1,
                    max_retries,
                )
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
        except Exception:
            import logging

            logging.error("❌ Ошибка в read_data", exc_info=True)
            raise

    return {}


def read_all_devices() -> List[Dict[str, Any]]:
    """Return snapshots for all registered devices."""
    with _lock, _connect() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM latest_data ORDER BY device_id")
        rows = cur.fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            updated_at = item.get("updated_at")
            if isinstance(updated_at, datetime):
                item["updated_at"] = updated_at.isoformat()
            result.append(item)
        return result


def get_db_health():
    """Проверка состояния базы данных"""
    try:
        with _connect() as conn:
            # Проверяем WAL режим
            cursor = conn.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]

            # Проверяем количество записей
            cursor = conn.execute("SELECT COUNT(*) FROM sensor_data;")
            sensor_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM latest_data;")
            latest_count = cursor.fetchone()[0]

            # Проверяем последнюю запись
            cursor = conn.execute("SELECT MAX(timestamp) FROM sensor_data;")
            last_record = cursor.fetchone()[0]

            return {
                "status": "healthy",
                "journal_mode": journal_mode,
                "sensor_records": sensor_count,
                "latest_records": latest_count,
                "last_update": last_record,
            }
    except Exception as e:
        import logging

        logging.error(f"❌ Ошибка проверки состояния БД: {e}")
        return {"status": "error", "error": str(e)}
