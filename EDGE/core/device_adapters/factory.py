#!/usr/bin/env python3
"""
Factory для создания адаптеров устройств
"""

from typing import Optional, Dict
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