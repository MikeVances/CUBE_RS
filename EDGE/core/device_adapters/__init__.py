"""
Device Adapters - паттерн для поддержки разных типов устройств
"""

from .base import DeviceAdapter, RegisterInfo, DeviceData
from .kub1063 import KUB1063Adapter  
from .kub1112 import KUB1112Adapter
from .factory import get_device_adapter

__all__ = [
    'DeviceAdapter',
    'RegisterInfo', 
    'DeviceData',
    'KUB1063Adapter',
    'KUB1112Adapter', 
    'get_device_adapter'
]