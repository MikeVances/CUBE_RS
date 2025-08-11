import sqlite3
import threading
from datetime import datetime

DB_FILE = "kub_data.db"

def _connect():
    """Create SQLite connection with WAL for safe concurrent access."""
    conn = sqlite3.connect(DB_FILE, timeout=5)
    # Enable WAL to reduce writer/reader blocking and improve concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
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
        cursor.execute(INSERT_SQL)
        conn.commit()

def update_data(**kwargs):
    """
    Частичное обновление: меняем только переданные поля из ALL_FIELDS и всегда обновляем updated_at.
    Пример: update_data(temp_inside=25.0, humidity=57.3)
    Неуказанные поля остаются без изменений.
    """
    # Filter only known columns
    cols = []
    vals = []
    for k, v in kwargs.items():
        if k in ALL_FIELDS:
            cols.append(f"{k} = ?")
            vals.append(v)
    # If nothing to update, just bump the timestamp and exit
    if not cols:
        with _lock, _connect() as conn:
            conn.execute("UPDATE latest_data SET updated_at = datetime('now') WHERE id = 1")
            conn.commit()
        return

    cols.append("updated_at = ?")
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    vals.append(current_time)
    set_clause = ", ".join(cols)
    with _lock, _connect() as conn:
        conn.execute(f"UPDATE latest_data SET {set_clause} WHERE id = 1", vals)
        conn.commit()

def read_data():
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