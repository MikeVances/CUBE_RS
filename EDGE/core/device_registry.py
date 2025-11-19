#!/usr/bin/env python3
"""
Device Registry - система регистрации и управления устройствами
Поддерживает разные типы устройств с разными картами регистров
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dataclasses import asdict, dataclass
from enum import Enum

from core.log_filter import get_secure_logger
from core.utils.paths import get_project_root

logger = get_secure_logger(__name__)

try:
    from modbus.modbus_storage import (
        read_data as read_modbus_data,
        read_registers_latest,
        init_db as init_modbus_db,
    )

    MODBUS_STORAGE_AVAILABLE = True
except Exception as e:  # pragma: no cover - optional dependency
    MODBUS_STORAGE_AVAILABLE = False
    read_modbus_data = None  # type: ignore
    read_registers_latest = None  # type: ignore
    init_modbus_db = None  # type: ignore
    logger.warning(f"⚠️ Modbus storage недоступен: {e}")


class DeviceType(Enum):
    """Поддерживаемые типы устройств"""
    KUB_1063 = "KUB-1063"  # Вентиляция
    KUB_1112 = "KUB-1112"  # Обогрев
    VFD_INVERTER = "VFD-INVERTER"  # Регулятор скорости / Частотный преобразователь
    UNKNOWN = "UNKNOWN"


@dataclass
class DeviceInfo:
    """Информация об устройстве"""
    device_id: int
    device_type: DeviceType
    slave_id: int
    name: str
    description: Optional[str] = None
    enabled: bool = True
    location: Optional[str] = None
    room: Optional[str] = None  # помещение/группа для UI/логики
    # Новые поля для DeviceScheduler
    poll_interval: Optional[float] = None  # Интервал опроса в секундах (None = дефолтный)
    priority: Optional[str] = None         # Приоритет: "HIGH", "NORMAL", "LOW", "CRITICAL"

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON/YAML"""
        result = asdict(self)
        result['device_type'] = self.device_type.value
        # Убираем None значения для чистого YAML
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceInfo':
        """Создание из словаря"""
        device_type_str = data.get('device_type', 'UNKNOWN')
        try:
            device_type = DeviceType(device_type_str)
        except ValueError:
            logger.warning(f"Неизвестный тип устройства: {device_type_str}")
            device_type = DeviceType.UNKNOWN

        return cls(
            device_id=data['device_id'],
            device_type=device_type,
            slave_id=data['slave_id'],
            name=data['name'],
            description=data.get('description'),
            enabled=data.get('enabled', True),
            location=data.get('location'),
            room=data.get('room'),
            poll_interval=data.get('poll_interval'),  # Новое поле
            priority=data.get('priority')             # Новое поле
        )


_MODBUS_STORAGE_INITIALIZED = False


class DeviceRegistry:
    """Реестр устройств в системе"""
    
    DEFAULT_CACHE_TTL = 5.0

    def __init__(self, config_path: Optional[Path] = None):
        self.project_root = get_project_root()
        self.config_path = config_path or (self.project_root / "config" / "devices.yaml")
        self.devices: Dict[int, DeviceInfo] = {}
        self._device_data_cache: Dict[int, Dict[str, Any]] = {}
        self._device_data_timestamp: Dict[int, float] = {}
        self.cache_ttl = self.DEFAULT_CACHE_TTL
        self.load_devices_from_config()

        if MODBUS_STORAGE_AVAILABLE:
            self._ensure_modbus_storage()

    def _load_devices(self):
        """Загрузка устройств из конфигурации"""
        try:
            self.devices.clear()
            if not self.config_path.exists():
                logger.info(f"Файл устройств не найден: {self.config_path}, создаём с дефолтными устройствами")
                self._create_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            devices_data = config.get('devices', [])
            for device_data in devices_data:
                device = DeviceInfo.from_dict(device_data)
                self.devices[device.device_id] = device
                logger.debug(f"Загружено устройство: {device.name} (ID: {device.device_id})")
            
            logger.info(f"✅ Загружено {len(self.devices)} устройств из {self.config_path}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки устройств: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Создание конфигурации по умолчанию"""
        default_devices = [
            DeviceInfo(
                device_id=1,
                device_type=DeviceType.KUB_1063,
                slave_id=1,
                name="Корпус 1 - Вентиляция",
                description="Система вентиляции и климата",
                location="Корпус №1"
            )
        ]
        
        for device in default_devices:
            self.devices[device.device_id] = device
        
        self.save_config()
        logger.info("✅ Создана конфигурация устройств по умолчанию")
    
    def save_config(self):
        """Сохранение конфигурации устройств"""
        try:
            # Создаём директорию если её нет
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            config = {
                'devices': [device.to_dict() for device in self.devices.values()]
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            logger.info(f"💾 Конфигурация устройств сохранена: {self.config_path}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфигурации: {e}")
    
    def load_devices_from_config(self) -> None:
        """Публичный метод обновления списка устройств из конфигурации"""
        self._load_devices()

    def _ensure_modbus_storage(self) -> None:
        """Гарантирует наличие таблиц в локальном хранилище Modbus."""
        global _MODBUS_STORAGE_INITIALIZED
        if _MODBUS_STORAGE_INITIALIZED:
            return
        if not init_modbus_db:
            logger.warning("⚠️ init_db для Modbus storage недоступен")
            return
        try:
            init_modbus_db()
            _MODBUS_STORAGE_INITIALIZED = True
            logger.info("📦 Modbus storage инициализирован")
        except Exception as exc:
            logger.warning(f"⚠️ Не удалось инициализировать modbus storage: {exc}")

    def register_device(self, device: DeviceInfo) -> bool:
        """Регистрация нового устройства"""
        if device.device_id in self.devices:
            logger.warning(f"Устройство с ID {device.device_id} уже существует")
            return False

        # Проверка на дублирование slave_id
        for existing_device in self.devices.values():
            if existing_device.slave_id == device.slave_id and existing_device.enabled:
                logger.warning(f"Slave ID {device.slave_id} уже используется устройством {existing_device.name}")
                return False
        
        self.devices[device.device_id] = device
        self.save_config()
        logger.info(f"✅ Зарегистрировано устройство: {device.name} (ID: {device.device_id})")
        return True
    
    def get_device(self, device_id: int) -> Optional[DeviceInfo]:
        """Получение информации об устройстве"""
        return self.devices.get(device_id)

    def get_devices(self, enabled_only: bool = True) -> List[DeviceInfo]:
        """Возвращает список устройств, совместимый с legacy кодом"""
        if enabled_only:
            return [device for device in self.devices.values() if device.enabled]
        return list(self.devices.values())

    def get_devices_by_type(self, device_type: DeviceType) -> List[DeviceInfo]:
        """Получение всех устройств определённого типа"""
        return [device for device in self.devices.values() 
                if device.device_type == device_type and device.enabled]

    def get_all_devices(self, enabled_only: bool = True) -> List[DeviceInfo]:
        """Получение всех устройств"""
        if enabled_only:
            return [device for device in self.devices.values() if device.enabled]
        return list(self.devices.values())
    
    def enable_device(self, device_id: int) -> bool:
        """Включение устройства"""
        if device_id not in self.devices:
            return False
        
        self.devices[device_id].enabled = True
        self.save_config()
        logger.info(f"✅ Устройство {device_id} включено")
        return True
    
    def disable_device(self, device_id: int) -> bool:
        """Отключение устройства"""
        if device_id not in self.devices:
            return False
        
        self.devices[device_id].enabled = False
        self.save_config()
        logger.info(f"⏸️ Устройство {device_id} отключено")
        return True
    
    def get_device_by_slave_id(self, slave_id: int) -> Optional[DeviceInfo]:
        """Поиск устройства по slave_id"""
        for device in self.devices.values():
            if device.slave_id == slave_id and device.enabled:
                return device
        return None

    # --- Работа с данными устройств -------------------------------------------------

    def _read_device_data(self, device: DeviceInfo) -> Optional[Dict[str, Any]]:
        """Чтение актуальных данных устройства из локального хранилища"""
        if not MODBUS_STORAGE_AVAILABLE:
            logger.debug("📦 Modbus storage недоступен — возвращаем None")
            return None

        try:
            raw_data = read_modbus_data(device.device_id)  # type: ignore[misc]
        except Exception as exc:
            logger.error(f"❌ Ошибка чтения modbus storage: {exc}")
            return None

        if not raw_data:
            return None

        data = dict(raw_data)
        registers_blob = data.pop("registers_blob", None)
        registers_payload: Dict[str, Any] = {}
        if isinstance(registers_blob, str) and registers_blob:
            try:
                registers_payload = json.loads(registers_blob)
            except Exception:
                logger.debug(
                    "⚠️ Не удалось распарсить registers_blob для устройства %s",
                    device.device_id,
                )
                registers_payload = {}
        alarms_blob = data.pop("alarms_json", None)
        warnings_blob = data.pop("warnings_json", None)
        alarms_list: list[Any] = []
        warnings_list: list[Any] = []
        if isinstance(alarms_blob, str) and alarms_blob:
            try:
                parsed = json.loads(alarms_blob)
                if isinstance(parsed, list):
                    alarms_list = parsed
            except Exception:
                logger.debug("⚠️ Не удалось распарсить alarms_json для устройства %s", device.device_id)
        if isinstance(warnings_blob, str) and warnings_blob:
            try:
                parsed = json.loads(warnings_blob)
                if isinstance(parsed, list):
                    warnings_list = parsed
            except Exception:
                logger.debug("⚠️ Не удалось распарсить warnings_json для устройства %s", device.device_id)
        updated_at = data.pop("updated_at", None)

        timestamp_dt: Optional[datetime] = None
        if isinstance(updated_at, datetime):
            timestamp_dt = updated_at
        elif isinstance(updated_at, str):
            try:
                timestamp_dt = datetime.fromisoformat(updated_at)
            except ValueError:
                timestamp_dt = None

        if timestamp_dt is None:
            timestamp_dt = datetime.utcnow()

        data["device_id"] = device.device_id
        data["device_name"] = device.name
        data["device_type"] = device.device_type.value
        iso_ts = timestamp_dt.isoformat()
        data["timestamp"] = iso_ts
        data["updated_at"] = iso_ts
        data.setdefault("status", "online")
        if alarms_list:
            data["alarms"] = alarms_list
            if not data.get("active_alarms"):
                data["active_alarms"] = len(alarms_list)
        if warnings_list:
            data["warnings"] = warnings_list

        # Включаем регистры (для VFD и т.д.)
        try:
            if registers_payload:
                data["registers"] = registers_payload
                for key, value in registers_payload.items():
                    data.setdefault(key, value)
            elif read_registers_latest:
                registers = read_registers_latest(device.device_id)
                if registers:
                    data["registers"] = {
                        str(reg.get("name") or reg.get("register")): reg.get("value")
                        for reg in registers
                        if reg.get("name") or reg.get("register") is not None
                    }
                    for key, value in data["registers"].items():
                        data.setdefault(key, value)
        except Exception as exc:
            logger.warning(f"⚠️ Не удалось прочитать регистры устройства {device.device_id}: {exc}")

        self._filter_metrics_for_device(device, data)
        return data

    def get_device_data(self, device_id: int, *, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Возвращает данные устройства с кэшированием"""
        device = self.devices.get(device_id)
        if not device:
            logger.debug(f"⚠️ Запрошены данные неизвестного устройства {device_id}")
            return None

        now = time.time()
        if not force_refresh:
            cached = self._device_data_cache.get(device_id)
            last_ts = self._device_data_timestamp.get(device_id, 0)
            if cached and now - last_ts < self.cache_ttl:
                return cached

        data = self._read_device_data(device)
        if data is not None:
            self._device_data_cache[device_id] = data
            self._device_data_timestamp[device_id] = now
            return data

        # Возвращаем последнюю кэшированную версию, если она была
        return self._device_data_cache.get(device_id)

    def refresh_all_device_data(self) -> Dict[int, Dict[str, Any]]:
        """Принудительное обновление данных всех устройств"""
        refreshed = {}
        for device in self.get_devices(enabled_only=True):
            data = self.get_device_data(device.device_id, force_refresh=True)
            if data:
                refreshed[device.device_id] = data
        return refreshed

    def _filter_metrics_for_device(self, device: DeviceInfo, data: Dict[str, Any]) -> None:
        from core.device_adapters.factory import get_device_metric_keys  # локальный импорт, чтобы избежать циклов

        allowed = get_device_metric_keys(device.device_type)
        always = {"connection_status", "last_error", "status", "timestamp", "updated_at", "device_id", "device_name", "device_type", "slave_id"}
        allowed.update(always)
        remove_keys = [key for key in data.keys() if key not in allowed and key != "registers"]
        for key in remove_keys:
            data.pop(key, None)
        if "registers" in data:
            regs = data["registers"] or {}
            if isinstance(regs, dict):
                data["registers"] = {k: v for k, v in regs.items() if k in allowed}

    # ---------------------------
    # Параметры планировщика
    # ---------------------------

    def get_custom_poll_intervals(self) -> Dict[int, float]:
        """Возвращает интервалы опроса, заданные в devices.yaml."""
        intervals: Dict[int, float] = {}
        for device_id, info in self.devices.items():
            if info.poll_interval is None:
                continue
            try:
                interval = float(info.poll_interval)
            except (TypeError, ValueError):
                logger.warning(
                    "⚠️ Некорректный poll_interval для устройства %s: %s",
                    device_id,
                    info.poll_interval,
                )
                continue
            if interval > 0:
                intervals[device_id] = interval
        return intervals

    def get_custom_poll_priorities(self) -> Dict[int, "PollPriority"]:
        """Возвращает приоритеты опроса, заданные в devices.yaml."""
        try:
            from core.device_scheduler import PollPriority  # локальный импорт, чтобы избежать циклов
        except Exception:
            logger.warning("⚠️ PollPriority недоступен, возвращаем пустые приоритеты")
            return {}

        priorities: Dict[int, PollPriority] = {}
        for device_id, info in self.devices.items():
            if not info.priority:
                continue

            priority_key = str(info.priority).upper().strip()
            try:
                priority_enum = PollPriority[priority_key]
            except KeyError:
                logger.warning(
                    "⚠️ Некорректный priority '%s' для устройства %s",
                    info.priority,
                    device_id,
                )
                continue

            priorities[device_id] = priority_enum

        return priorities


# Глобальный экземпляр реестра
_device_registry: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    """Получение глобального экземпляра реестра устройств"""
    global _device_registry
    if _device_registry is None:
        _device_registry = DeviceRegistry()
    return _device_registry


def reload_device_registry():
    """Перезагрузка реестра устройств"""
    global _device_registry
    _device_registry = None
    return get_device_registry()
