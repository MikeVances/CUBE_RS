"""
file: EDGE/modbus/command_queue.py
description: Унифицированная очередь команд записи Modbus, доступная ботом и дашбордом.
author: Mike Vance & EDGE Full-Stack RS485 Senior Engineer GPT
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from core.config_manager import get_config
from core.log_filter import get_secure_logger
from core.utils.paths import resolve_under_root

logger = get_secure_logger(__name__)

_DB_INIT_LOCK = threading.Lock()
_DB_READY = False
_SCHEMA_VERIFIED = False


@dataclass
class WriteCommand:
    """Структура команды записи Modbus."""

    id: str
    device_id: Optional[int]
    slave_id: Optional[int]
    register: int
    value: int
    priority: int
    created_at: datetime
    scheduled_at: Optional[datetime]
    attempts: int
    max_attempts: int
    status: str
    user_info: Optional[str]
    source: Optional[str]
    error_message: Optional[str]


def _db_path() -> Path:
    cfg = get_config()
    return Path(resolve_under_root(cfg.database.commands_db))


def _ensure_db() -> None:
    global _DB_READY, _SCHEMA_VERIFIED
    path = _db_path()
    if _DB_READY and _SCHEMA_VERIFIED:
        return
    with _DB_INIT_LOCK:
        if not _DB_READY:
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS write_commands (
                        id TEXT PRIMARY KEY,
                        device_id INTEGER,
                        slave_id INTEGER,
                        register INTEGER NOT NULL,
                        value INTEGER NOT NULL,
                        source_ip TEXT,
                        source_port INTEGER,
                        user_info TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        scheduled_at TIMESTAMP,
                        executed_at TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        attempts INTEGER DEFAULT 0,
                        max_attempts INTEGER DEFAULT 3,
                        priority INTEGER DEFAULT 0,
                        error_message TEXT,
                        execution_time_ms INTEGER
                    )
                    """
                )
            _DB_READY = True
            logger.info("🗃️ Command queue storage ready: %s", path)
        if not _SCHEMA_VERIFIED:
            with sqlite3.connect(path) as conn:
                _ensure_columns(conn)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_commands_status ON write_commands(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_commands_priority ON write_commands(priority DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_commands_created ON write_commands(created_at)"
                )
            _SCHEMA_VERIFIED = True


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Best-effort миграции для обновлённой схемы."""

    existing = {row[1] for row in conn.execute("PRAGMA table_info(write_commands)")}
    added = 0
    required_columns = {
        "device_id": "INTEGER",
        "slave_id": "INTEGER",
        "priority": "INTEGER DEFAULT 0",
        "attempts": "INTEGER DEFAULT 0",
        "max_attempts": "INTEGER DEFAULT 3",
        "status": "TEXT DEFAULT 'pending'",
        "error_message": "TEXT",
        "execution_time_ms": "INTEGER",
        "scheduled_at": "TIMESTAMP",
        "source_ip": "TEXT",
        "source_port": "INTEGER",
    }
    for column, ddl in required_columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE write_commands ADD COLUMN {column} {ddl}")
            added += 1
    if added:
        logger.info("🔧 write_commands schema extended with %s new columns", added)


def enqueue_register_write(
    *,
    device_id: Optional[int] = None,
    slave_id: Optional[int] = None,
    register: int,
    value: int,
    user_info: Optional[str] = None,
    source: Optional[str] = None,
    priority: int = 1,
    scheduled_at: Optional[datetime] = None,
    max_attempts: int = 3,
) -> str:
    """Поставить команду записи в очередь.

    source — произвольная строка (например, "telegram" или "dashboard").
    Возвращает id команды, который можно отобразить пользователю.
    """

    _ensure_db()
    command_id = uuid.uuid4().hex[:12]
    created_at = datetime.utcnow().isoformat()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO write_commands
            (id, device_id, slave_id, register, value, user_info, created_at, status, priority,
             scheduled_at, max_attempts, attempts, error_message, source_ip, source_port)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, 0, NULL, ?, NULL)
            """,
            (
                command_id,
                device_id,
                slave_id,
                register,
                value,
                user_info,
                created_at,
                priority,
                scheduled_at.isoformat() if scheduled_at else None,
                max_attempts,
                source,
            ),
        )
    logger.info(
        "📝 Enqueued write command id=%s reg=0x%04X val=%s source=%s",
        command_id,
        register,
        value,
        source or "unknown",
    )
    return command_id


def fetch_pending_commands(limit: int = 10) -> List[WriteCommand]:
    """Считать pending-команды по приоритету."""

    _ensure_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, device_id, slave_id, register, value, priority, created_at,
                   scheduled_at, attempts, max_attempts, status, user_info,
                   source_ip AS source, error_message
            FROM write_commands
            WHERE status IN ('pending', 'failed')
              AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)
              AND attempts < max_attempts
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    commands: List[WriteCommand] = []
    for row in rows:
        commands.append(
            WriteCommand(
                id=row["id"],
                device_id=row["device_id"],
                slave_id=row["slave_id"],
                register=row["register"],
                value=row["value"],
                priority=row["priority"],
                created_at=datetime.fromisoformat(row["created_at"]),
                scheduled_at=datetime.fromisoformat(row["scheduled_at"]) if row["scheduled_at"] else None,
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                status=row["status"],
                user_info=row["user_info"],
                source=row["source"],
                error_message=row["error_message"],
            )
        )
    return commands


def mark_executing(command_id: str) -> None:
    """Отметить команду как выполняемую."""

    _ensure_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            UPDATE write_commands
            SET status = 'executing', attempts = attempts + 1, scheduled_at = NULL
            WHERE id = ?
            """,
            (command_id,),
        )


def mark_completed(command_id: str, execution_time_ms: Optional[int] = None) -> None:
    """Отметить команду выполненной."""

    _ensure_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            UPDATE write_commands
            SET status = 'completed', executed_at = CURRENT_TIMESTAMP,
                execution_time_ms = ?, error_message = NULL
            WHERE id = ?
            """,
            (execution_time_ms, command_id),
        )


def mark_failed(command_id: str, error_message: str, retry_in_seconds: Optional[int] = None) -> None:
    """Отметить команду как проваленную и, при необходимости, перенести выполнение."""

    _ensure_db()
    scheduled_at = None
    if retry_in_seconds:
        scheduled_at = datetime.utcnow().timestamp() + retry_in_seconds
        scheduled_at = datetime.utcfromtimestamp(scheduled_at).isoformat()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            UPDATE write_commands
            SET status = 'failed', error_message = ?, scheduled_at = ?, executed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error_message[:500], scheduled_at, command_id),
        )


def get_recent_commands(limit: int = 5) -> List[dict[str, Any]]:
    """Вернуть последние выполненные/ожидающие команды для UI."""

    _ensure_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, register, value, status, created_at, executed_at, user_info,
                   error_message, attempts, priority, device_id, slave_id
            FROM write_commands
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        result.append({key: row[key] for key in row.keys()})
    return result


def reset_stuck_commands(max_age_seconds: int = 120) -> int:
    """Переводит зависшие executing-команды обратно в pending.

    Используется при рестарте executor'а или при его падении, чтобы очередь не замирала.
    Возвращает количество команд, переведённых в pending.
    """

    _ensure_db()
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    cutoff_iso = cutoff.isoformat()
    with sqlite3.connect(_db_path()) as conn:
        cursor = conn.execute(
            """
            UPDATE write_commands
            SET status = 'pending', scheduled_at = CURRENT_TIMESTAMP, error_message = 'auto-reset (stuck)'
            WHERE status = 'executing' AND (executed_at IS NULL OR executed_at < ?) AND created_at < ?
            """,
            (cutoff_iso, cutoff_iso),
        )
        affected = cursor.rowcount or 0
    if affected:
        logger.warning("♻️ %s stuck commands reset to pending", affected)
    return affected


__all__ = [
    "enqueue_register_write",
    "fetch_pending_commands",
    "mark_executing",
    "mark_completed",
    "mark_failed",
    "get_recent_commands",
    "reset_stuck_commands",
    "WriteCommand",
]
