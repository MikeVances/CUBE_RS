"""Device adapter helpers and dynamic re-exports."""

from importlib import import_module

from .base import DeviceAdapter, RegisterInfo, DeviceData
from .factory import get_device_adapter
from .catalog import DEVICE_DEFINITIONS

__all__ = ['DeviceAdapter', 'RegisterInfo', 'DeviceData', 'get_device_adapter']

for definition in DEVICE_DEFINITIONS:
    module_name, class_name = definition.adapter.rsplit('.', 1)
    module = import_module(module_name)
    cls = getattr(module, class_name)
    globals()[class_name] = cls
    __all__.append(class_name)
