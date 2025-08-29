import sqlite3
import threading
import time
from datetime import datetime

DB_FILE = "kub_data.db"

def _connect():
    """Create SQLite connection with WAL for safe concurrent access."""
    conn = sqlite3.connect(DB_FILE, timeout=10)  # Увеличен таймаут до 10 сек
    # Enable WAL to reduce writer/reader blocking and improve concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    # Добавляем дополнительные настройки для безопасности
    conn.execute("PRAGMA busy_timeout=5000;")  # 5 секунд ожидания при блокировке
    conn.execute("PRAGMA cache_size=-64000;")   # 64MB кэша для производительности
    return conn

_lock = threading.Lock()

# Все регистры из Cube-1063_modbus registers.md (Input Registers)
ALL_FIELDS = [
    "software_version",  # 0x0301
    "digital_outputs_1",  # 0x0081
    "digital_outputs_2",  # 0x0082
    "digital_outputs_3",  # 0x00A2
    "pressure",           # 0x0083
    "humidity",           # 0x0084
    "co2",                # 0x0085
    "nh3",                # 0x0086
    "grv_base",           # 0x0087
    "grv_tunnel",         # 0x0088
    "damper",             # 0x0089
    # 0x008A–0x009B пропущены (групповые)
    "active_alarms",      # 0x00C3
    "registered_alarms",  # 0x00C7
    "active_warnings",    # 0x00CB
    "registered_warnings",# 0x00CF
    "ventilation_target", # 0x00D0
    "ventilation_level",  # 0x00D1
    "ventilation_scheme", # 0x00D2
    "day_counter",        # 0x00D3
    "temp_target",        # 0x00D4
    "temp_inside",        # 0x00D5
    "temp_vent_activation", # 0x00D6
    # + updated_at
]

CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS latest_data (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    software_version TEXT,
    digital_outputs_1 INTEGER,
    digital_outputs_2 INTEGER,
    digital_outputs_3 INTEGER,
    pressure REAL,
    humidity REAL,
    co2 INTEGER,
    nh3 REAL,
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
    updated_at TIMESTAMP
);
'''

CREATE_HISTORY_SQL = '''
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    software_version TEXT,
    digital_outputs_1 INTEGER,
    digital_outputs_2 INTEGER,
    digital_outputs_3 INTEGER,
    pressure REAL,
    humidity REAL,
    co2 INTEGER,
    nh3 REAL,
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
'''

INSERT_SQL = '''
INSERT OR IGNORE INTO latest_data (id, updated_at)
VALUES (1, datetime('now'))
'''

SELECT_SQL = f'''
SELECT {', '.join(ALL_FIELDS)}, updated_at FROM latest_data WHERE id = 1
'''

def init_db():
    with _lock, _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(CREATE_SQL)
        cursor.execute(CREATE_HISTORY_SQL)
        cursor.execute(INSERT_SQL)
        conn.commit()

def update_data(**kwargs):
    """
    Частичное обновление: меняем только переданные поля из ALL_FIELDS и всегда обновляем updated_at.
    Пример: update_data(temp_inside=25.0, humidity=57.3)
    Неуказанные поля остаются без изменений.
    """
    import logging
    logging.info(f"🔍 update_data вызван с {len(kwargs)} параметрами: {list(kwargs.keys())}")
    
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
            conn.execute("UPDATE latest_data SET updated_at = datetime('now') WHERE id = 1")
            conn.commit()
        return

    cols.append("updated_at = ?")
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
                sensor_keys = [k for k in kwargs.keys() if k in ['temp_inside', 'humidity', 'co2', 'pressure']]
                if sensor_keys:
                    logging.info(f"🔍 Найдены ключи сенсоров: {sensor_keys}, добавляем в историю")
                    
                    # Добавляем в историю В ТОМ ЖЕ соединении, чтобы избежать deadlock
                    valid_data = {k: v for k, v in kwargs.items() if k in ALL_FIELDS and v is not None}
                    logging.info(f"🔍 Отфильтровано {len(valid_data)} валидных полей: {list(valid_data.keys())}")
                    
                    if valid_data:
                        columns = list(valid_data.keys())
                        values = list(valid_data.values())
                        placeholders = ', '.join(['?' for _ in values])
                        columns_str = ', '.join(columns)
                        
                        sql = f"INSERT INTO sensor_data ({columns_str}) VALUES ({placeholders})"
                        logging.info(f"🔍 SQL для истории: {sql[:100]}...")
                        
                        conn.execute(sql, values)
                        logging.info("✅ Запись в sensor_data выполнена")
                    
                    logging.info("✅ Запись в историю выполнена")
                else:
                    logging.info("🔍 Ключи сенсоров не найдены, пропускаем историю")
                
                conn.commit()
                logging.info("✅ update_data завершена успешно")
                break  # Успешное выполнение, выходим из цикла
                
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logging.warning(f"⚠️ БД заблокирована, попытка {attempt + 1}/{max_retries}")
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
    logging.info(f"🔍 Отфильтровано {len(valid_data)} валидных полей: {list(valid_data.keys())}")
    
    if not valid_data:
        logging.warning("⚠️ Нет валидных данных для записи в историю")
        return
    
    columns = list(valid_data.keys())
    values = list(valid_data.values())
    placeholders = ', '.join(['?' for _ in values])
    columns_str = ', '.join(columns)
    
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
                logging.warning(f"⚠️ БД заблокирована при чтении, попытка {attempt + 1}/{max_retries}")
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
                "last_update": last_record
            }
    except Exception as e:
        import logging
        logging.error(f"❌ Ошибка проверки состояния БД: {e}")
        return {
            "status": "error",
            "error": str(e)
        }