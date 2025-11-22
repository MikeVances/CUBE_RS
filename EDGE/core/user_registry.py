#!/usr/bin/env python3
"""Примитивный реестр пользователей EDGE для общего доступа разных интерфейсов."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from core.config_manager import get_config


def _resolve_commands_db() -> str:
    """Путь к базе, где уже хранится Telegram Bot (commands_db)."""

    try:
        cfg = get_config()
        db_path = getattr(cfg.database, "commands_db", None)
        if db_path:
            return str(Path(db_path).expanduser())
    except Exception:
        pass

    # Fallback — храним рядом с остальными данными
    return str(Path("data/commands.db").resolve())


def _hash_pin(pin: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()
    return digest, salt


@dataclass
class EdgeUser:
    id: int
    display_name: str
    role: str
    is_active: bool
    telegram_id: Optional[int] = None


class UserRegistry:
    """Утилитарный доступ к таблицам edge_users и журналам."""

    def __init__(self, db_file: Optional[str] = None) -> None:
        self.db_file = db_file or _resolve_commands_db()
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    pin_hash TEXT,
                    pin_salt TEXT,
                    telegram_id INTEGER,
                    email TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    client TEXT,
                    session_token TEXT,
                    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    logout_time TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES edge_users(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_user_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actor_user_id INTEGER,
                    target_user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    success INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (actor_user_id) REFERENCES edge_users(id),
                    FOREIGN KEY (target_user_id) REFERENCES edge_users(id)
                )
                """
            )

    def list_users(self, active_only: bool = True) -> List[EdgeUser]:
        query = "SELECT id, display_name, role, is_active, telegram_id FROM edge_users"
        params: Iterable = ()
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY display_name"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [EdgeUser(*row) for row in rows]

    def create_user(self, display_name: str, pin: str, role: str = "user", telegram_id: Optional[int] = None) -> int:
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported role: {role}")
        pin_hash, salt = _hash_pin(pin)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO edge_users (display_name, role, pin_hash, pin_salt, telegram_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (display_name, role, pin_hash, salt, telegram_id),
            )
            user_id = cur.lastrowid
            self._write_audit(conn, actor_user_id=None, target_user_id=user_id, action="create_user", details=display_name)
            return int(user_id)

    def set_pin(self, user_id: int, pin: str, actor_id: Optional[int] = None) -> None:
        pin_hash, salt = _hash_pin(pin)
        with self._connect() as conn:
            conn.execute(
                "UPDATE edge_users SET pin_hash=?, pin_salt=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (pin_hash, salt, user_id),
            )
            self._write_audit(conn, actor_user_id=actor_id, target_user_id=user_id, action="set_pin", details="manual")

    def authenticate(self, user_id: int, pin: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT pin_hash, pin_salt, is_active FROM edge_users WHERE id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return False
        pin_hash, salt, is_active = row
        if not pin_hash or not is_active:
            return False
        candidate, _ = _hash_pin(pin, salt)
        return secrets.compare_digest(candidate, pin_hash)

    def update_user(
        self,
        user_id: int,
        *,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        telegram_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> None:
        fields = []
        values = []
        if display_name is not None:
            fields.append("display_name = ?")
            values.append(display_name)
        if role is not None:
            if role not in ALLOWED_ROLES:
                raise ValueError(f"Unsupported role: {role}")
            fields.append("role = ?")
            values.append(role)
        if telegram_id is not None:
            fields.append("telegram_id = ?")
            values.append(telegram_id)
        if is_active is not None:
            fields.append("is_active = ?")
            values.append(1 if is_active else 0)

        if not fields:
            return

        values.append(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE edge_users SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                tuple(values),
            )
            self._write_audit(
                conn,
                actor_user_id=None,
                target_user_id=user_id,
                action="update_user",
                details=",".join(fields),
            )

    def find_user(self, user_id: int) -> Optional[EdgeUser]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, display_name, role, is_active, telegram_id FROM edge_users WHERE id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return EdgeUser(*row)

    def get_user_by_telegram(self, telegram_id: int) -> Optional[EdgeUser]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, display_name, role, is_active, telegram_id FROM edge_users WHERE telegram_id=?",
                (telegram_id,),
            ).fetchone()
        return EdgeUser(*row) if row else None

    def ensure_default_admin(self, pin: str = "0000") -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM edge_users WHERE role='admin' LIMIT 1").fetchone()
            if row:
                return row[0]
            cur = conn.execute(
                """
                INSERT INTO edge_users (display_name, role, is_active)
                VALUES ('Администратор', 'admin', 0)
                """
            )
            admin_id = cur.lastrowid
            pin_hash, salt = _hash_pin(pin)
            conn.execute(
                "UPDATE edge_users SET pin_hash=?, pin_salt=?, is_active=1 WHERE id=?",
                (pin_hash, salt, admin_id),
            )
            self._write_audit(conn, actor_user_id=None, target_user_id=admin_id, action="bootstrap_admin", details="auto")
            return int(admin_id)

    def create_invitation(
        self,
        *,
        invited_by: Optional[int],
        role: str = "user",
        hours_valid: int = 24,
    ) -> str:
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported role: {role}")
        code = secrets.token_hex(4)
        expires_at = datetime.utcnow() + timedelta(hours=max(1, hours_valid))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_invitations (invitation_code, invited_by, access_level, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, invited_by, role, expires_at.isoformat()),
            )
        return code

    def list_invitations(self, active_only: bool = True) -> List[dict[str, Any]]:
        query = "SELECT invitation_code, access_level, created_at, expires_at, is_active FROM user_invitations"
        params: Iterable = ()
        if active_only:
            query += " WHERE is_active = 1 AND used_by IS NULL"
        query += " ORDER BY created_at DESC LIMIT 50"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result = []
        for code, level, created_at, expires_at, is_active in rows:
            result.append(
                {
                    "code": code,
                    "access_level": level,
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "is_active": bool(is_active),
                }
            )
        return result

    def _write_audit(
        self,
        conn: sqlite3.Connection,
        *,
        actor_user_id: Optional[int],
        target_user_id: Optional[int],
        action: str,
        details: Optional[str] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO edge_user_audit (actor_user_id, target_user_id, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (actor_user_id, target_user_id, action, details),
        )
ALLOWED_ROLES: Sequence[str] = ("user", "operator", "engineer", "admin")
