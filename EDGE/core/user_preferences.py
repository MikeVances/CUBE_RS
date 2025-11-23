#!/usr/bin/env python3
"""
file: EDGE/core/user_preferences.py
description: Unified storage/access layer for per-user UI/Telegram preferences.
author: EDGE Full-Stack RS485 Senior Engineer GPT
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config_manager import get_config

logger = logging.getLogger(__name__)


DEFAULT_PREFERENCES: Dict[str, Any] = {
    "rooms": {},
    "auto_refresh": {"enabled": True, "interval": 60},
}


def _sanitize_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Нормализует структуру настроек: комнаты → устройства → список метрик."""

    data = payload or {}
    rooms_source = data.get("rooms", {}) if isinstance(data, dict) else {}
    rooms_clean: Dict[str, Dict[int, List[str]]] = {}
    if isinstance(rooms_source, dict):
        for room, devices in rooms_source.items():
            if not isinstance(devices, dict):
                continue
            room_devices: Dict[int, List[str]] = {}
            for device_id_raw, metrics in devices.items():
                try:
                    device_id = int(device_id_raw)
                except Exception:
                    continue
                if isinstance(metrics, list):
                    room_devices[device_id] = [
                        str(metric) for metric in metrics if isinstance(metric, str)
                    ]
            rooms_clean[str(room)] = room_devices

    auto_raw = data.get("auto_refresh", {}) if isinstance(data, dict) else {}
    auto_section = {
        "enabled": bool(auto_raw.get("enabled", True)),
        "interval": int(auto_raw.get("interval", 60) or 60),
    }

    normalized = {
        "rooms": rooms_clean,
        "auto_refresh": auto_section,
    }
    return normalized


@dataclass
class PreferenceRecord:
    user_id: int
    payload: Dict[str, Any]
    updated_at: datetime


class UserPreferencesService:
    """Persists dashboard/Telegram preferences in a single SQLite table."""

    TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS edge_user_preferences (
        user_id INTEGER PRIMARY KEY,
        payload TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES edge_users(id) ON DELETE CASCADE
    )
    """

    def __init__(self, db_file: Optional[str] = None) -> None:
        cfg = get_config()
        self.db_file = db_file or cfg.database.commands_db
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(self.TABLE_SQL)

    def load(self, user_id: int) -> PreferenceRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, payload, updated_at FROM edge_user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except Exception:
            payload = {}
        updated = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow()
        return PreferenceRecord(
            user_id=row["user_id"], payload=_sanitize_payload(payload), updated_at=updated
        )

    def save(self, user_id: int, payload: Dict[str, Any]) -> None:
        normalized = _sanitize_payload(payload)
        serialized = json.dumps(normalized, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO edge_user_preferences (user_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, serialized),
            )

    def delete(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM edge_user_preferences WHERE user_id = ?", (user_id,))

    # -------- High-level helpers ---------

    def get_preferences(self, user_id: int) -> Dict[str, Any]:
        record = self.load(user_id)
        if record:
            payload = dict(record.payload)
            payload["_updated_at"] = record.updated_at.isoformat()
            return payload
        fallback = DEFAULT_PREFERENCES.copy()
        fallback["_updated_at"] = datetime.utcnow().isoformat()
        return fallback

    def set_preferences(self, user_id: int, payload: Dict[str, Any]) -> None:
        self.save(user_id, payload)

    def toggle_metric(
        self,
        user_id: int,
        room: str,
        device_id: int,
        metric_key: str,
        enabled: bool,
    ) -> Dict[str, Any]:
        prefs = self.get_preferences(user_id)
        room_bucket = prefs.setdefault("rooms", {}).setdefault(room, {})
        device_metrics = room_bucket.setdefault(int(device_id), [])
        metric_key = str(metric_key)
        if enabled and metric_key not in device_metrics:
            device_metrics.append(metric_key)
        elif not enabled and metric_key in device_metrics:
            device_metrics.remove(metric_key)
        self.save(user_id, prefs)
        return prefs

    def set_device_metrics(
        self,
        user_id: int,
        room: str,
        device_id: int,
        metrics: List[str],
    ) -> Dict[str, Any]:
        prefs = self.get_preferences(user_id)
        room_bucket = prefs.setdefault("rooms", {}).setdefault(room, {})
        room_bucket[int(device_id)] = [str(m) for m in metrics]
        self.save(user_id, prefs)
        return prefs


_service: Optional[UserPreferencesService] = None


def get_user_preferences_service() -> UserPreferencesService:
    global _service
    if _service is None:
        _service = UserPreferencesService()
    return _service
