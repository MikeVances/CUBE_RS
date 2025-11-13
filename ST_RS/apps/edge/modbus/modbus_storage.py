import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path


def _resolve_db_path() -> str:
    """Resolve SQLite DB path for EDGE deployment (inside EDGE/ subtree).

    Priority:
    1) DATABASE_URL=sqlite:///absolute/or/relative/path.db (resolved against repo root if relative)
    2) core.config_manager database.file (resolved against repo root if relative)
    3) repo_root/data/kub_data.db
    """
    # 1) DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        p = Path(db_url.replace("sqlite:///", "", 1))
        if p.is_absolute():
            return str(p)
        repo_root = Path(__file__).resolve().parents[5]
        target = repo_root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)

    # 2) core.config_manager
    try:
        from core.config_manager import get_config  # type: ignore

        cfg = get_config()
        db_file = getattr(cfg.database, "file", None) or "kub_data.db"
        p = Path(db_file)
        if not p.is_absolute():
            repo_root = Path(__file__).resolve().parents[5]
            target = repo_root / p
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target)
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    except Exception:
        pass

    # 3) Default to repo_root/data/kub_data.db
    repo_root = Path(__file__).resolve().parents[5]
    target = repo_root / "data" / "kub_data.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)


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
ALL_FIELDS = [
    # Системная информация
    "software_version",   # 0x0301
    "factory_number",     # 0x0302
    "device_number",      # 0x0303
    
    # Цифровые выходы
    "digital_outputs_1",  # 0x0081
    "digital_outputs_2",  # 0x0082
    "digital_outputs_3",  # 0x00A2
    
    # Основные датчики
    "pressure",           # 0x0083
    "pressure_status",    # статус датчика давления
    "humidity",           # 0x0084
    "humidity_status",    # статус датчика влажности
    "co2",               # 0x0085
    "co2_status",        # статус датчика CO2
    "nh3",               # 0x0086
    "nh3_status",        # статус датчика NH3
    
    # Управляющие выходы
    "grv_base",          # 0x0087
    "grv_tunnel",        # 0x0088
    "damper",            # 0x0089
    
    # Воздухозаборники
    "air_intake_1",      # 0x008A
    "air_intake_2",      # 0x008B
    "air_intake_tunnel", # 0x008C
    "air_intake_3",      # 0x0092
    "air_intake_4",      # 0x0093
    
    # Температурные датчики
    "temp_inside_1",     # 0x008D
    "temp_inside_2",     # 0x008E
    "temp_outside",      # 0x008F
    "temp_inside_3",     # 0x0090
    "temp_inside_4",     # 0x0091
    
    # Освещение
    "lighting_1",        # 0x0094
    "lighting_2",        # 0x0095
    "lighting_3",        # 0x0096
    "lighting_4",        # 0x0097
    
    # Таймеры
    "timer_1_output_1",  # 0x0098
    "timer_1_output_2",  # 0x0099
    "timer_1_output_3",  # 0x009A
    "timer_1_output_4",  # 0x009B
    "timer_2_output_1",  # 0x009C
    "timer_2_output_2",  # 0x009D
    "timer_2_output_3",  # 0x009E
    "timer_2_output_4",  # 0x009F
    
    # Аварии и предупреждения
    "active_alarms",     # 0x00C3
    "registered_alarms", # 0x00C7
    "active_warnings",   # 0x00CB
    "registered_warnings", # 0x00CF
    
    # Система вентиляции
    "ventilation_target", # 0x00D0
    "ventilation_level",  # 0x00D1
    "ventilation_scheme", # 0x00D2
    "day_counter",        # 0x00D3
    
    # Температурная система
    "temp_target",        # 0x00D4
    "temp_inside",        # 0x00D5
    "temp_vent_activation", # 0x00D6
]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS latest_data (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    -- Системная информация
    software_version TEXT,
    factory_number TEXT,
    device_number INTEGER,
    -- Цифровые выходы
    digital_outputs_1 INTEGER,
    digital_outputs_2 INTEGER,
    digital_outputs_3 INTEGER,
    -- Основные датчики
    pressure REAL,
    pressure_status TEXT,
    humidity REAL,
    humidity_status TEXT,
    co2 INTEGER,
    co2_status TEXT,
    nh3 REAL,
    nh3_status TEXT,
    -- Управляющие выходы
    grv_base REAL,
    grv_tunnel REAL,
    damper REAL,
    -- Воздухозаборники
    air_intake_1 REAL,
    air_intake_2 REAL,
    air_intake_tunnel REAL,
    air_intake_3 REAL,
    air_intake_4 REAL,
    -- Температурные датчики
    temp_inside_1 REAL,
    temp_inside_2 REAL,
    temp_outside REAL,
    temp_inside_3 REAL,
    temp_inside_4 REAL,
    -- Освещение
    lighting_1 REAL,
    lighting_2 REAL,
    lighting_3 REAL,
    lighting_4 REAL,
    -- Таймеры
    timer_1_output_1 REAL,
    timer_1_output_2 REAL,
    timer_1_output_3 REAL,
    timer_1_output_4 REAL,
    timer_2_output_1 REAL,
    timer_2_output_2 REAL,
    timer_2_output_3 REAL,
    timer_2_output_4 REAL,
    -- Аварии и предупреждения
    active_alarms INTEGER,
    registered_alarms INTEGER,
    active_warnings INTEGER,
    registered_warnings INTEGER,
    -- Система вентиляции
    ventilation_target REAL,
    ventilation_level REAL,
    ventilation_scheme TEXT,
    day_counter INTEGER,
    -- Температурная система
    temp_target REAL,
    temp_inside REAL,
    temp_vent_activation REAL,
    -- Метка времени
    updated_at TIMESTAMP
);
"""

CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    software_version TEXT,
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
    temp_vent_activation REAL
);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO latest_data (id, updated_at)
VALUES (1, datetime('now'))
"""

SELECT_SQL = f"""
SELECT {', '.join(ALL_FIELDS)}, updated_at FROM latest_data WHERE id = 1
"""


def init_db():
    with _lock, _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(CREATE_SQL)
        cursor.execute(CREATE_HISTORY_SQL)
        cursor.execute(INSERT_SQL)

        # Миграция: добавляем недостающие колонки статусов при обновлении
        def _ensure_column(table: str, col: str, col_type: str):
            cur = conn.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

        for t in ("latest_data", "sensor_data"):
            _ensure_column(t, "pressure_status", "TEXT")
            _ensure_column(t, "humidity_status", "TEXT")
            _ensure_column(t, "co2_status", "TEXT")
            _ensure_column(t, "nh3_status", "TEXT")
        conn.commit()


def update_data(**kwargs):
    """
    Частичное обновление: меняем только переданные поля из ALL_FIELDS и всегда обновляем updated_at.
    Пример: update_data(temp_inside=25.0, humidity=57.3)
    Неуказанные поля остаются без изменений.
    """
    import logging

    logging.info(
        f"🔍 update_data вызван с {len(kwargs)} параметрами: {list(kwargs.keys())}"
    )

    # Filter only known columns
    cols = []
    vals = []
    for k, v in kwargs.items():
        if k in ALL_FIELDS:
            cols.append(f"{k} = ?")
            vals.append(v)
            logging.info(f"🔍 Добавлен параметр {k}={v}")

    # If nothing to update, just bump the timestamp and exit
    if not cols:
        logging.info("🔍 Нет полей для обновления, обновляем только timestamp")
        with _lock, _connect() as conn:
            conn.execute(
                "UPDATE latest_data SET updated_at = datetime('now') WHERE id = 1"
            )
            conn.commit()
        return

    cols.append("updated_at = ?")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vals.append(current_time)
    set_clause = ", ".join(cols)

    logging.info(f"🔍 SQL запрос: UPDATE latest_data SET {set_clause[:100]}...")

    # Механизм безопасности: повторные попытки при блокировке
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with _lock, _connect() as conn:
                # Начинаем транзакцию
                conn.execute("BEGIN IMMEDIATE;")

                # Обновляем latest_data
                conn.execute(f"UPDATE latest_data SET {set_clause} WHERE id = 1", vals)
                logging.info("✅ latest_data обновлена")

                # Добавляем в историю sensor_data, если есть существенные данные
                sensor_keys = [
                    k
                    for k in kwargs.keys()
                    if k in ["temp_inside", "humidity", "co2", "pressure"]
                ]
                if sensor_keys:
                    logging.info(
                        f"🔍 Найдены ключи сенсоров: {sensor_keys}, добавляем в историю"
                    )

                    # Добавляем в историю В ТОМ ЖЕ соединении, чтобы избежать deadlock
                    valid_data = {
                        k: v
                        for k, v in kwargs.items()
                        if k in ALL_FIELDS and v is not None
                    }
                    logging.info(
                        f"🔍 Отфильтровано {len(valid_data)} валидных полей: {list(valid_data.keys())}"
                    )

                    if valid_data:
                        columns = list(valid_data.keys())
                        values = list(valid_data.values())
                        placeholders = ", ".join(["?" for _ in values])
                        columns_str = ", ".join(columns)

                        sql = f"INSERT INTO sensor_data ({columns_str}) VALUES ({placeholders})"
                        logging.info(f"🔍 SQL для истории: {sql[:100]}...")

                        conn.execute(sql, values)
                        logging.info("✅ Запись в sensor_data выполнена")

                    logging.info("✅ Запись в историю выполнена")
                else:
                    logging.info("🔍 Ключи сенсоров не найдены, пропускаем историю")

                # Обновляем KV‑снимок регистров на основе известной карты
                try:
                    _update_registers_snapshot_tx(conn, kwargs)
                except Exception as e:
                    logging.warning(f"⚠️ Не удалось обновить KV регистры: {e}")

                conn.commit()
                logging.info("✅ update_data завершена успешно")
                break  # Успешное выполнение, выходим из цикла

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logging.warning(
                    f"⚠️ БД заблокирована, попытка {attempt + 1}/{max_retries}"
                )
                time.sleep(0.1 * (attempt + 1))  # Экспоненциальная задержка
                continue
            else:
                logging.error(f"❌ Ошибка блокировки БД: {e}")
                raise
        except Exception as e:
            logging.error(f"❌ Ошибка в update_data: {e}")
            import traceback

            logging.error(traceback.format_exc())
            raise


def add_history_record(**kwargs):
    """Добавляет запись в историческую таблицу sensor_data"""
    import logging

    logging.info(f"🔍 add_history_record вызван с {len(kwargs)} параметрами")

    # Filter only known columns
    valid_data = {k: v for k, v in kwargs.items() if k in ALL_FIELDS and v is not None}
    logging.info(
        f"🔍 Отфильтровано {len(valid_data)} валидных полей: {list(valid_data.keys())}"
    )

    if not valid_data:
        logging.warning("⚠️ Нет валидных данных для записи в историю")
        return

    columns = list(valid_data.keys())
    values = list(valid_data.values())
    placeholders = ", ".join(["?" for _ in values])
    columns_str = ", ".join(columns)

    sql = f"INSERT INTO sensor_data ({columns_str}) VALUES ({placeholders})"
    logging.info(f"🔍 SQL для истории: {sql[:100]}...")

    try:
        with _lock, _connect() as conn:
            conn.execute(sql, values)
            conn.commit()
            logging.info("✅ Запись в sensor_data выполнена")
    except Exception as e:
        logging.error(f"❌ Ошибка записи в sensor_data: {e}")
        import traceback

        logging.error(traceback.format_exc())
        raise


def read_data():
    """Безопасное чтение данных с повторными попытками"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with _lock, _connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(SELECT_SQL)
                row = cursor.fetchone()
                if not row:
                    return {}
                data = {f: row[f] for f in ALL_FIELDS}
                updated_at = row["updated_at"]
                if isinstance(updated_at, datetime):
                    updated_at = updated_at.isoformat()
                data["updated_at"] = updated_at
                return data
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                import logging

                logging.warning(
                    f"⚠️ БД заблокирована при чтении, попытка {attempt + 1}/{max_retries}"
                )
                time.sleep(0.05 * (attempt + 1))
                continue
            else:
                import logging

                logging.error(f"❌ Ошибка чтения БД: {e}")
                raise
        except Exception as e:
            import logging

            logging.error(f"❌ Ошибка в read_data: {e}")
            raise

    return {}  # Если все попытки неудачны


def _update_registers_snapshot_tx(conn: sqlite3.Connection, data: dict):
    """Обновляет таблицы registers_latest и registers_history в рамках уже открытой транзакции.

    - Гарантирует наличие таблиц (CREATE TABLE IF NOT EXISTS)
    - Берёт карту регистров из YAML (name -> {address, display})
    - Для присутствующих в data значений делает UPSERT в registers_latest и вставку в registers_history
    """
    # 1) Гарантируем наличие таблиц
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registers_latest (
            register INTEGER PRIMARY KEY,
            name TEXT,
            value TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registers_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            register INTEGER,
            name TEXT,
            value TEXT
        )
        """
    )

    try:
        # 2) Загружаем карту регистров из конфигурации
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

        rows_latest = []
        rows_history = []

        for name, meta in reg_meta.items():
            if name not in data:
                continue
            value = data.get(name)
            addr_str = meta.get("address")
            try:
                addr = int(addr_str, 16) if isinstance(addr_str, str) and addr_str.startswith("0x") else int(addr_str)
            except Exception:
                continue

            val_text = "" if value is None else str(value)
            rows_latest.append((addr, name, val_text, now))
            rows_history.append((addr, name, val_text))

        if rows_latest:
            conn.executemany(
                """
                INSERT INTO registers_latest (register, name, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(register) DO UPDATE SET
                    name=excluded.name,
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                rows_latest,
            )

        if rows_history:
            conn.executemany(
                "INSERT INTO registers_history (register, name, value) VALUES (?, ?, ?)",
                rows_history,
            )

    except Exception as e:
        import logging

        logging.warning(f"⚠️ KV обновление регистров пропущено: {e}")


def read_registers_latest() -> list[dict]:
    """Возвращает список всех регистров (register, name, value, updated_at).

    Если таблица ещё не создана (например, дашборд поднялся раньше первого update_data),
    создаёт её и возвращает пустой список.
    """
    with _lock, _connect() as conn:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT register, name, value, updated_at FROM registers_latest ORDER BY register"
            )
            return [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError as e:
            if "no such table: registers_latest" in str(e).lower():
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registers_latest (
                        register INTEGER PRIMARY KEY,
                        name TEXT,
                        value TEXT,
                        updated_at TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registers_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        register INTEGER,
                        name TEXT,
                        value TEXT
                    )
                    """
                )
                conn.commit()
                return []
            raise


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
