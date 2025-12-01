"""
file: EDGE/modbus/command_executor.py
description: Фоновый исполнитель очереди команд Modbus с верификацией и логированием пользователей.
author: Mike Vance & EDGE Full-Stack RS485 Senior Engineer GPT
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from core.config_manager import get_config
from core.device_registry import DeviceInfo, DeviceRegistry
from core.log_filter import get_secure_logger
from modbus.command_queue import (
    WriteCommand,
    fetch_pending_commands,
    mark_completed,
    mark_executing,
    mark_failed,
    reset_stuck_commands,
)
from modbus.reader_integration import submit_universal_write

logger = get_secure_logger(__name__)


@dataclass
class ExecutorSettings:
    """Настройки исполнителя команд, загружаемые из конфига."""

    poll_interval: float = 1.0
    batch_size: int = 5
    retry_delay_seconds: int = 15
    write_timeout: float = 8.0
    verify_after_write: bool = True


class CommandExecutor:
    """Фоновый исполнитель write_commands, использующий Universal Reader."""

    def __init__(
        self,
        *,
        device_registry: Optional[DeviceRegistry] = None,
        settings: Optional[ExecutorSettings] = None,
    ) -> None:
        self.device_registry = device_registry or DeviceRegistry()
        self.settings = settings or self._load_settings()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _load_settings(self) -> ExecutorSettings:
        cfg = get_config()
        section = getattr(cfg, "command_executor", None)
        settings = ExecutorSettings()
        if not section:
            return settings
        for field in ("poll_interval", "batch_size", "retry_delay_seconds", "write_timeout", "verify_after_write"):
            value = getattr(section, field, None)
            if value is None:
                continue
            try:
                setattr(settings, field, type(getattr(settings, field))(value))
            except Exception:
                logger.warning("⚠️ Невозможно применить command_executor.%s=%s", field, value)
        return settings

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        reset_stuck_commands()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="command-executor", daemon=True)
        self._thread.start()
        logger.info("🚀 CommandExecutor запущен (poll=%.1fs, batch=%s)", self.settings.poll_interval, self.settings.batch_size)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("🛑 CommandExecutor остановлен")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                commands = fetch_pending_commands(limit=self.settings.batch_size)
            except Exception as exc:
                logger.error("❌ Ошибка чтения очереди команд: %s", exc)
                time.sleep(self.settings.poll_interval)
                continue

            if not commands:
                self._stop_event.wait(self.settings.poll_interval)
                continue

            for command in commands:
                if self._stop_event.is_set():
                    break
                self._process_command(command)

    def _process_command(self, command: WriteCommand) -> None:
        device = self._resolve_device(command)
        if not device:
            logger.error(
                "❌ Команда %s отклонена: не найдено устройство (device_id=%s, slave_id=%s)",
                command.id,
                command.device_id,
                command.slave_id,
            )
            mark_failed(command.id, "device_not_found", retry_in_seconds=None)
            return

        target_slave = device.slave_id
        mark_executing(command.id)
        started = time.monotonic()
        logger.info(
            "✍️ [%s] Выполняем команду %s: reg=0x%04X val=%s device_id=%s slave_id=%s user=%s",
            command.source or "unknown",
            command.id,
            command.register,
            command.value,
            device.device_id,
            target_slave,
            command.user_info or "anonymous",
        )

        success, error_message = self._execute_command(device, command)
        duration_ms = int((time.monotonic() - started) * 1000)

        if success:
            mark_completed(command.id, duration_ms)
            logger.info(
                "✅ Команда %s выполнена за %d мс (user=%s)",
                command.id,
                duration_ms,
                command.user_info or "anonymous",
            )
        else:
            retry = self.settings.retry_delay_seconds if command.attempts + 1 < command.max_attempts else None
            mark_failed(command.id, error_message or "write_failed", retry_in_seconds=retry)
            logger.warning(
                "⚠️ Команда %s не выполнена (%s). attempts=%s/%s",
                command.id,
                error_message,
                command.attempts + 1,
                command.max_attempts,
            )

    def _execute_command(self, device: DeviceInfo, command: WriteCommand) -> tuple[bool, Optional[str]]:
        finished = threading.Event()
        result = {"success": False, "error": None}

        def _callback(success: bool, error: Optional[str], verification) -> None:
            result["success"] = success
            result["error"] = error
            finished.set()

        ok = submit_universal_write(
            register=command.register,
            value=command.value,
            device_info=device,
            callback=_callback,
            verify=self.settings.verify_after_write,
        )

        if not ok:
            return False, "enqueue_failed"
        if not finished.wait(self.settings.write_timeout):
            return False, "write_timeout"
        if not result["success"]:
            return False, result["error"] or "write_failed"
        return True, None

    def _resolve_device(self, command: WriteCommand) -> Optional[DeviceInfo]:
        if command.device_id:
            candidate = self.device_registry.get_device(command.device_id)
            if candidate and candidate.enabled:
                return candidate
        if command.slave_id:
            candidate = self.device_registry.get_device_by_slave_id(command.slave_id)
            if candidate:
                return candidate
        devices = self.device_registry.get_all_devices(enabled_only=True)
        return devices[0] if devices else None


__all__ = ["CommandExecutor", "ExecutorSettings"]
