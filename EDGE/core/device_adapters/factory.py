#!/usr/bin/env python3
"""
Factory для создания адаптеров устройств
"""

from typing import Optional, Dict, Set, Any
from importlib import import_module
from enum import Enum

from .base import DeviceAdapter
from core.device_adapters.catalog import DEVICE_DEFINITIONS


# Реестр доступных адаптеров
_ADAPTER_REGISTRY: Dict[str, type] = {}
for definition in DEVICE_DEFINITIONS:
    module_name, class_name = definition.adapter.rsplit('.', 1)
    module = import_module(module_name)
    adapter_cls = getattr(module, class_name)
    _ADAPTER_REGISTRY[definition.type] = adapter_cls

# Кэш экземпляров адаптеров
_adapter_cache: Dict[str, DeviceAdapter] = {}


def get_device_adapter(device_type: Enum | str) -> Optional[DeviceAdapter]:
    """
    Получение адаптера для типа устройства
    
    Args:
        device_type: Тип устройства
        
    Returns:
        DeviceAdapter или None если тип не поддерживается
    """
    type_key = device_type.value if isinstance(device_type, Enum) else str(device_type)
    if type_key == "UNKNOWN":
        return None
    
    # Проверяем кэш
    if type_key in _adapter_cache:
        return _adapter_cache[type_key]
    
    # Создаём новый адаптер
    adapter_class = _ADAPTER_REGISTRY.get(type_key)
    if adapter_class is None:
        return None
    
    adapter = adapter_class()
    _adapter_cache[type_key] = adapter
    
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
    # Fallback: позволяем адаптеру объявлять дополнительные метрики вручную
    extra_metadata = getattr(adapter, "extra_metric_metadata", None)
    if callable(extra_metadata):
        try:
            extra = extra_metadata()
        except Exception:
            extra = None
    else:
        extra = extra_metadata
    if isinstance(extra, dict):
        for name, info in extra.items():
            entry = metadata.setdefault(name, {})
            if isinstance(info, dict):
                entry.update({k: v for k, v in info.items() if v is not None})
            else:
                entry.setdefault("label", str(info))

    device_type = getattr(adapter, "device_type", "")
    if device_type == "KUB-1063":
        technical_suffixes = ("_relay_channel", "_signal_channel", "_input_channel")
        technical_keys = {"relay_assignments"}
        for key, entry in metadata.items():
            if key.endswith(technical_suffixes) or key in technical_keys:
                entry["hidden"] = True
    return metadata


def get_device_metric_keys(device_type: Enum | str) -> Set[str]:
    """Return set of metric keys relevant for the adapter of this device type."""
    adapter = get_device_adapter(device_type)
    keys: Set[str] = set()
    if not adapter:
        return keys

    metadata = _collect_adapter_metadata(adapter)
    keys.update(metadata.keys())
    return keys


def get_device_metric_metadata(device_type: Enum | str) -> Dict[str, Dict[str, Any]]:
    adapter = get_device_adapter(device_type)
    if not adapter:
        return {}
    return _collect_adapter_metadata(adapter)


def get_alarm_catalog(device_type: Enum | str) -> Dict[int, Dict[str, Any]]:
    adapter = get_device_adapter(device_type)
    if not adapter:
        return {}
    catalog = getattr(adapter, "get_alarm_catalog", None)
    if callable(catalog):
        try:
            data = catalog()
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    raw_catalog = getattr(adapter, "alarm_catalog", None)
    if isinstance(raw_catalog, dict):
        return raw_catalog
    return {}


def get_supported_device_types() -> list[str]:
    """Получение списка поддерживаемых типов устройств"""
    return list(_ADAPTER_REGISTRY.keys())


def register_adapter(device_type: Enum | str, adapter_class: type):
    """
    Регистрация нового адаптера
    
    Args:
        device_type: Тип устройства
        adapter_class: Класс адаптера (должен наследоваться от DeviceAdapter)
    """
    if not issubclass(adapter_class, DeviceAdapter):
        raise ValueError("Adapter class must inherit from DeviceAdapter")

    type_key = device_type.value if isinstance(device_type, Enum) else str(device_type)
    _ADAPTER_REGISTRY[type_key] = adapter_class

    if type_key in _adapter_cache:
        del _adapter_cache[type_key]


def clear_adapter_cache():
    """Очистка кэша адаптеров"""
    global _adapter_cache
    _adapter_cache.clear()
