#!/usr/bin/env python3
"""Интеграция Universal Modbus Reader в архитектуру EDGE с очередями."""

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from core.log_filter import get_secure_logger
from core.device_registry import DeviceInfo, get_device_registry
from modbus.universal_reader import UniversalModbusReader

logger = get_secure_logger(__name__)

ReadCallback = Callable[[Optional[Dict[str, Any]]], None]
WriteCallback = Callable[[bool, Optional[str], Optional[Dict[str, Any]]], None]


@dataclass
class _ReadTask:
    device: DeviceInfo
    callback: ReadCallback
    submitted_at: float = field(default_factory=time.time)


@dataclass
class _WriteTask:
    device: DeviceInfo
    register: int
    value: int
    callback: Optional[WriteCallback] = None
    verify: bool = True
    submitted_at: float = field(default_factory=time.time)


_global_reader: Optional[UniversalModbusReader] = None
_read_queue: "queue.Queue[_ReadTask]" = queue.Queue()
_write_queue: "queue.Queue[_WriteTask]" = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_worker_stop_event = threading.Event()
_worker_lock = threading.Lock()


def initialize_reader(port: str, baudrate: int = 9600, timeout: float = 2.0) -> bool:
    """
    Инициализация глобального reader'а

    Args:
        port: Serial порт (напр. /dev/ttyUSB0)
        baudrate: Скорость передачи
        timeout: Таймаут чтения

    Returns:
        True если инициализация успешна
    """
    global _global_reader

    try:
        _stop_worker()
        _global_reader = UniversalModbusReader(port=port, baudrate=baudrate, timeout=timeout)

        if _global_reader.connect():
            logger.info(f"✅ Universal Modbus Reader инициализирован на {port}")
            _reset_queues()
            _start_worker()
            return True

        logger.error(f"❌ Не удалось подключиться к {port}")
        return False

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации reader: {e}")
        return False


def request_universal_read(
    callback: Callable[[Optional[Dict[str, Any]]], None],
    device_info: Optional[DeviceInfo] = None,
    device_id: Optional[int] = None,
    slave_id: Optional[int] = None
) -> None:
    """
    Универсальный запрос чтения устройства
    Совместим с legacy интерфейсом request_rs485_read_all

    Args:
        callback: Функция обратного вызова с результатом
        device_info: Информация об устройстве (приоритет)
        device_id: ID устройства в registry
        slave_id: Modbus Slave ID (fallback)
    """
    device = _resolve_device(device_info, device_id, slave_id)
    if not device:
        callback(None)
        return

    if not _ensure_worker_ready():
        logger.error("❌ Universal Reader не готов к работе")
        callback(None)
        return

    _read_queue.put(_ReadTask(device=device, callback=callback))


def request_rs485_read_all_universal(
    callback: Callable[[Optional[Dict[str, Any]]], None],
    slave_id: int
) -> None:
    """
    Legacy-совместимая функция для замены request_rs485_read_all
    Использует Universal Reader вместо старого кода

    Args:
        callback: Функция обратного вызова
        slave_id: Modbus Slave ID устройства
    """
    request_universal_read(callback=callback, slave_id=slave_id)


def read_device_sync(device_info: DeviceInfo) -> Optional[Dict[str, Any]]:
    """
    Синхронное чтение устройства

    Args:
        device_info: Информация об устройстве

    Returns:
        Dict с данными устройства или None
    """
    result: Dict[str, Optional[Dict[str, Any]]] = {"data": None}
    done = threading.Event()

    def _cb(data: Optional[Dict[str, Any]]) -> None:
        result["data"] = data
        done.set()

    request_universal_read(_cb, device_info=device_info)
    done.wait(timeout=10)
    return result["data"]


def read_all_devices_sync() -> Dict[int, Dict[str, Any]]:
    """
    Синхронное чтение всех активных устройств из registry

    Returns:
        Dict[device_id] = device_data
    """
    registry = get_device_registry()
    devices = registry.get_all_devices(enabled_only=True)

    if not devices:
        logger.warning("⚠️ Нет активных устройств для чтения")
        return {}

    logger.info(f"📡 Читаем {len(devices)} устройств синхронно...")

    results: Dict[int, Dict[str, Any]] = {}
    for device in devices:
        data = read_device_sync(device)
        if data:
            results[device.device_id] = data

    logger.info(f"✅ Прочитано {len(results)} из {len(devices)} устройств")
    return results


def submit_universal_write(
    *,
    register: int,
    value: int,
    device_info: Optional[DeviceInfo] = None,
    device_id: Optional[int] = None,
    slave_id: Optional[int] = None,
    callback: Optional[WriteCallback] = None,
    verify: bool = True,
) -> bool:
    """Поставить запись регистра в очередь с приоритетом."""

    device = _resolve_device(device_info, device_id, slave_id)
    if not device:
        if callback:
            callback(False, "device_not_found", None)
        return False

    if register is None:
        if callback:
            callback(False, "register_not_specified", None)
        return False

    if not _ensure_worker_ready():
        if callback:
            callback(False, "reader_not_ready", None)
        return False

    task = _WriteTask(device=device, register=register, value=value, callback=callback, verify=verify)
    _write_queue.put(task)
    logger.debug(
        "✍️ Задача записи добавлена (device_id=%s, register=0x%04X, value=%s)",
        device.device_id,
        register,
        value,
    )
    return True


def shutdown_reader():
    """Корректно останавливает worker и закрывает reader."""
    global _global_reader

    _stop_worker()

    if _global_reader:
        try:
            _global_reader.disconnect()
            logger.info("🔌 Universal Modbus Reader закрыт")
        except Exception as e:
            logger.error(f"⚠️ Ошибка при закрытии reader: {e}")
        finally:
            _global_reader = None


# Экспортируем legacy-совместимую функцию
request_rs485_read_all = request_rs485_read_all_universal


def _resolve_device(
    device_info: Optional[DeviceInfo],
    device_id: Optional[int],
    slave_id: Optional[int],
) -> Optional[DeviceInfo]:
    if device_info:
        return device_info

    registry = get_device_registry()

    if device_id:
        device = registry.get_device(device_id)
        if device:
            return device
    if slave_id:
        device = registry.get_device_by_slave_id(slave_id)
        if device:
            return device

    logger.error(
        "❌ Устройство не найдено (device_id=%s, slave_id=%s)",
        device_id,
        slave_id,
    )
    return None


def _ensure_worker_ready() -> bool:
    if not _global_reader:
        return False
    if _worker_thread and _worker_thread.is_alive():
        return True
    _start_worker()
    return _worker_thread is not None and _worker_thread.is_alive()


def _reset_queues() -> None:
    global _read_queue, _write_queue, _worker_stop_event
    _read_queue = queue.Queue()
    _write_queue = queue.Queue()
    _worker_stop_event = threading.Event()


def _start_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        if not _global_reader:
            return

        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="universal-bus-worker")
        _worker_thread.start()


def _stop_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        _worker_stop_event.set()
        _worker_thread.join(timeout=3)
    _worker_thread = None


def _worker_loop() -> None:
    logger.info("🌀 Universal bus worker запущен")
    while not _worker_stop_event.is_set():
        drained_write = False
        try:
            while True:
                task = _write_queue.get_nowait()
                drained_write = True
                _process_write_task(task)
                _write_queue.task_done()
        except queue.Empty:
            pass

        if drained_write:
            continue

        try:
            read_task = _read_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        _process_read_task(read_task)
        _read_queue.task_done()

    logger.info("🛑 Universal bus worker остановлен")


def _process_read_task(task: _ReadTask) -> None:
    if not _global_reader:
        task.callback(None)
        return
    try:
        data = _global_reader.read_device(task.device)
    except Exception as exc:
        logger.error("❌ Ошибка чтения %s: %s", task.device.name, exc)
        data = None

    try:
        task.callback(data)
    except Exception as exc:
        logger.error("⚠️ Ошибка callback чтения: %s", exc)


def _process_write_task(task: _WriteTask) -> None:
    if not _global_reader:
        if task.callback:
            task.callback(False, "reader_not_ready", None)
        return

    success = False
    error_msg: Optional[str] = None
    verification: Optional[Dict[str, Any]] = None

    try:
        success = _global_reader.write_single_register(
            task.device.slave_id,
            task.register,
            task.value,
        )
        if not success:
            error_msg = "write_failed"
    except Exception as exc:
        success = False
        error_msg = str(exc)

    if success and task.verify:
        try:
            verification = _global_reader.read_device(task.device)
        except Exception as exc:
            logger.error(
                "⚠️ Ошибка верификации после записи (device_id=%s): %s",
                task.device.device_id,
                exc,
            )
            error_msg = f"verify_failed: {exc}"

    if task.callback:
        try:
            task.callback(success, error_msg, verification)
        except Exception as exc:
            logger.error("⚠️ Ошибка callback записи: %s", exc)
