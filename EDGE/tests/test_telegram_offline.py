#!/usr/bin/env python3
"""Integration checks for Telegram bot in offline mode."""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-token-for-tests")

EDGE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(EDGE_ROOT))
sys.path.insert(0, str(EDGE_ROOT.parent))

from core.telegram.bot_main import KUBTelegramBot  # noqa: E402


class DummyBotDB:
    """Minimal stub to bypass real DB initialisation."""

    def __init__(self, *args, **kwargs):
        self.db_file = "stub.db"


@pytest.fixture(autouse=True)
def patch_bot_db(monkeypatch):
    monkeypatch.setattr("core.telegram.bot_main.TelegramBotDB", DummyBotDB)
    yield


def _prepare_latest_data_db(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE latest_data (
                device_id INTEGER PRIMARY KEY,
                slave_id INTEGER,
                device_type TEXT,
                connection_status TEXT,
                last_error TEXT,
                temp_inside REAL,
                temp_target REAL,
                humidity REAL,
                co2 REAL,
                nh3 REAL,
                pressure REAL,
                ventilation_level REAL,
                ventilation_target REAL,
                active_alarms INTEGER,
                active_warnings INTEGER,
                updated_at TEXT,
                digital_outputs_1 INTEGER,
                digital_outputs_2 INTEGER,
                digital_outputs_3 INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO latest_data (
                device_id, slave_id, device_type, connection_status, last_error,
                temp_inside, temp_target, humidity, co2, nh3, pressure,
                ventilation_level, ventilation_target, active_alarms, active_warnings,
                updated_at, digital_outputs_1, digital_outputs_2, digital_outputs_3
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "KUB-1063",
                "connected",
                None,
                27.6,
                27.0,
                55.2,
                1745,
                0.0,
                21.8,
                12,
                15,
                0,
                0,
                "2024-01-01T12:00:00",
                0,
                1 << 7,
                0,
            ),
        )
        conn.commit()


def _prepare_sensor_history_db(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                slave_id INTEGER,
                co2 REAL,
                humidity REAL,
                nh3 REAL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Imitate sensor dropout (None) and later recovery (value)
        conn.executemany(
            "INSERT INTO sensor_data (device_id, slave_id, co2, humidity, nh3, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, None, None, None, "2024-01-01T12:00:00"),
                (1, 1, 1800, 50.0, 0.0, "2024-01-01T12:05:00"),
            ],
        )
        conn.commit()


@pytest.mark.asyncio
async def test_get_current_data_from_db_offline(tmp_path, monkeypatch):
    db_path = tmp_path / "kub_data.db"
    _prepare_latest_data_db(db_path)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    bot = KUBTelegramBot(token="dummy")
    bot.config.database.file = str(db_path)
    data = await bot.get_current_data_from_db()

    assert data is not None
    assert data["temp_inside"] == pytest.approx(27.6)
    assert data["alarm_relay"] is True
    assert data["alarm_relay_label"]

    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.mark.asyncio
async def test_get_recent_sensor_recovery(tmp_path, monkeypatch):
    db_path = tmp_path / "kub_history.db"
    _prepare_sensor_history_db(db_path)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    bot = KUBTelegramBot(token="dummy")
    bot.config.database.file = str(db_path)
    recovery = await bot.get_recent_sensor_recovery(minutes=60)

    assert recovery == {"co2": True, "humidity": True, "nh3": True}

    monkeypatch.delenv("DATABASE_URL", raising=False)
