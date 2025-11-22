#!/usr/bin/env python3
"""Device catalog loader – describes available adapters and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List
import re

import yaml


@dataclass
class DeviceDefinition:
    type: str
    adapter: str
    poll_interval: float = 20.0
    autoscan_probes: List[Dict[str, Any]] = field(default_factory=list)


def _sanitize_device_type_name(type_str: str) -> str:
    name = re.sub(r"[^0-9A-Za-z]+", "_", type_str).strip("_")
    return name.upper() or "DEVICE"


def _load_catalog() -> List[DeviceDefinition]:
    path = Path(__file__).with_name("device_catalog.yaml")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    definitions: List[DeviceDefinition] = []
    for entry in raw:
        definitions.append(
            DeviceDefinition(
                type=entry["type"],
                adapter=entry["adapter"],
                poll_interval=float(entry.get("poll_interval", 20.0)),
                autoscan_probes=entry.get("autoscan_probes") or [],
            )
        )
    return definitions


DEVICE_DEFINITIONS = _load_catalog()
DEVICE_DEFINITION_BY_TYPE: Dict[str, DeviceDefinition] = {
    d.type: d for d in DEVICE_DEFINITIONS
}
DEVICE_ENUM_NAME_MAP: Dict[str, str] = {
    d.type: _sanitize_device_type_name(d.type) for d in DEVICE_DEFINITIONS
}


def sanitize_device_type_name(type_str: str) -> str:
    return DEVICE_ENUM_NAME_MAP.get(type_str, _sanitize_device_type_name(type_str))


def import_adapter_class(definition: DeviceDefinition):
    module_name, class_name = definition.adapter.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, class_name)
