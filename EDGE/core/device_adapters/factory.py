#!/usr/bin/env python3
"""
Factory для создания адаптеров устройств
"""

from typing import Optional, Dict, Set, Any
from .base import DeviceAdapter
from .kub1063 import KUB1063Adapter
from .kub1112 import KUB1112Adapter
from .vfd_inverter import VFDInverterAdapter
from core.device_registry import DeviceType


# Реестр доступных адаптеров
_ADAPTER_REGISTRY: Dict[DeviceType, type] = {
    DeviceType.KUB_1063: KUB1063Adapter,
    DeviceType.KUB_1112: KUB1112Adapter,
    DeviceType.VFD_INVERTER: VFDInverterAdapter,
}

# Кэш экземпляров адаптеров
_adapter_cache: Dict[DeviceType, DeviceAdapter] = {}


def get_device_adapter(device_type: DeviceType) -> Optional[DeviceAdapter]:
    """
    Получение адаптера для типа устройства
    
    Args:
        device_type: Тип устройства
        
    Returns:
        DeviceAdapter или None если тип не поддерживается
    """
    if device_type == DeviceType.UNKNOWN:
        return None
    
    # Проверяем кэш
    if device_type in _adapter_cache:
        return _adapter_cache[device_type]
    
    # Создаём новый адаптер
    adapter_class = _ADAPTER_REGISTRY.get(device_type)
    if adapter_class is None:
        return None
    
    adapter = adapter_class()
    _adapter_cache[device_type] = adapter
    
    return adapter


def _collect_adapter_metadata(adapter: DeviceAdapter) -> Dict[str, Dict[str, Any]]:
    metadata: Dict[str, Dict[str, Any]] = {}

    variable_mapper = getattr(adapter, "variable_mapper", None)
    if variable_mapper is not None:
        try:
            refs = getattr(variable_mapper, "variable_references", {})
            type_defs = getattr(variable_mapper, "type_definitions", {})
            for name, ref in refs.items():
                entry: Dict[str, Any] = {}
                if ref.description:
                    entry["label"] = ref.description
                type_def = type_defs.get(ref.type_id)
                if type_def and getattr(type_def, "unit", None):
                    entry["unit"] = type_def.unit
                if entry:
                    metadata[name] = entry
        except Exception:
            pass

    reg_map = getattr(adapter, "register_map", None)
    if callable(reg_map):
        reg_map = reg_map()
    if isinstance(reg_map, dict):
        for name, info in reg_map.items():
            entry = metadata.setdefault(name, {})
            if not entry.get("label") and getattr(info, "description", None):
                entry["label"] = info.description
            if not entry.get("unit") and getattr(info, "unit", None):
                entry["unit"] = info.unit
    return metadata


def get_device_metric_keys(device_type: DeviceType) -> Set[str]:
    """Return set of metric keys relevant for the adapter of this device type."""
    adapter = get_device_adapter(device_type)
    keys: Set[str] = set()
    if not adapter:
        return keys

    metadata = _collect_adapter_metadata(adapter)
    keys.update(metadata.keys())
    return keys


def get_device_metric_metadata(device_type: DeviceType) -> Dict[str, Dict[str, Any]]:
    adapter = get_device_adapter(device_type)
    if not adapter:
        return {}
    return _collect_adapter_metadata(adapter)


def get_supported_device_types() -> list[DeviceType]:
    """Получение списка поддерживаемых типов устройств"""
    return list(_ADAPTER_REGISTRY.keys())


def register_adapter(device_type: DeviceType, adapter_class: type):
    """
    Регистрация нового адаптера
    
    Args:
        device_type: Тип устройства
        adapter_class: Класс адаптера (должен наследоваться от DeviceAdapter)
    """
    if not issubclass(adapter_class, DeviceAdapter):
        raise ValueError(f"Adapter class must inherit from DeviceAdapter")
    
    _ADAPTER_REGISTRY[device_type] = adapter_class
    
    # Очищаем кэш для этого типа
    if device_type in _adapter_cache:
        del _adapter_cache[device_type]


def clear_adapter_cache():
    """Очистка кэша адаптеров"""
    global _adapter_cache
    _adapter_cache.clear()
