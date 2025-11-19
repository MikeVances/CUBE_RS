"""
file: services/room_data.py
description: Агрегация данных устройств DeviceRegistry по помещениям для главного дашборда.
author: Streamlit Analytics Engineer GPT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from core.device_registry import DeviceInfo, DeviceRegistry
from core.device_adapters.factory import get_device_metric_keys, get_device_metric_metadata

UNASSIGNED_ROOM_NAME = "Без помещения"
FLATTENABLE_FIELDS = {"registers", "metrics", "values"}
ALLOWED_TOP_LEVEL_KEYS = {"connection_status", "last_error"}
DEVICE_STATUS_FIELDS = {
    "connection_status",
    "last_error",
    "status",
    "active_alarms",
    "active_warnings",
    "registered_alarms",
    "registered_warnings",
    "fault_code",
    "alarms",
    "warnings",
}
_DEVICE_METRIC_CACHE: Dict[str, set[str]] = {}
_DEVICE_METADATA_CACHE: Dict[str, Dict[str, "MetricMeta"]] = {}


@dataclass
class MetricRecord:
    """Представление отдельного измерения внутри помещения."""

    value: Any
    device_id: Optional[int] = None
    device_type: Optional[str] = None
    timestamp: Optional[datetime] = None

@dataclass
class MetricMeta:
    label: Optional[str] = None
    unit: Optional[str] = None


@dataclass
class DeviceStatus:
    connection_status: Optional[str] = None
    last_error: Optional[str] = None
    status: Optional[str] = None
    active_alarms: Optional[int] = None
    active_warnings: Optional[int] = None
    registered_alarms: Optional[int] = None
    registered_warnings: Optional[int] = None
    fault_code: Optional[Any] = None
    alarms: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None


@dataclass
class RoomSnapshot:
    """Снимок состояния помещения с агрегированными показателями."""

    room: str
    location: str
    devices: List[DeviceInfo] = field(default_factory=list)
    metrics: Dict[str, MetricRecord] = field(default_factory=dict)
    device_metrics: Dict[int, Dict[str, MetricRecord]] = field(default_factory=dict)
    device_statuses: Dict[int, DeviceStatus] = field(default_factory=dict)
    metric_metadata: Dict[int, Dict[str, MetricMeta]] = field(default_factory=dict)
    alarms: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None


def _parse_timestamp(raw_value: Any) -> Optional[datetime]:
    """Переводит timestamp из payload в datetime, если возможно."""
    if isinstance(raw_value, datetime):
        return raw_value
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value))
    except Exception:
        return None


def _normalize_counter(value: Any) -> int:
    """Приводит поле тревог/предупреждений к целому количеству."""
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set)):
        return len(value)
    try:
        return int(value)
    except Exception:
        return 0


def _record_device_status(
    snapshot: RoomSnapshot,
    device_id: int,
    status_key: str,
    value: Any,
    timestamp: Optional[datetime],
) -> None:
    status = snapshot.device_statuses.setdefault(device_id, DeviceStatus())
    if status_key in {"active_alarms", "active_warnings"}:
        value = _normalize_counter(value)
        setattr(status, status_key, value)
    elif status_key in {"alarms", "warnings"}:
        if value is None:
            value = []
        elif not isinstance(value, list):
            value = [str(value)]
        setattr(status, status_key, value)
        if status_key == "alarms" and value:
            status.active_alarms = max(len(value), status.active_alarms or 0)
    else:
        setattr(status, status_key, value)
    if timestamp and (status.timestamp is None or timestamp > status.timestamp):
        status.timestamp = timestamp


@st.cache_data(ttl=2.0, show_spinner=False, hash_funcs={DeviceRegistry: lambda _: "device_registry"})
def build_room_snapshots(registry: DeviceRegistry) -> List[RoomSnapshot]:
    """
    Собирает данные всех устройств и группирует их по помещению.

    :param registry: глобальный DeviceRegistry
    :return: список RoomSnapshot, пригодный для отображения на главной странице
    """
    rooms: Dict[str, RoomSnapshot] = {}

    for device in registry.get_devices(enabled_only=True):
        room_name = device.room or UNASSIGNED_ROOM_NAME
        snapshot = rooms.setdefault(
            room_name,
            RoomSnapshot(
                room=room_name,
                location=device.location or "—",
            ),
        )
        snapshot.devices.append(device)

        payload = registry.get_device_data(device.device_id) or {}
        payload_ts = _parse_timestamp(payload.get("timestamp"))
        if payload_ts and (snapshot.timestamp is None or payload_ts > snapshot.timestamp):
            snapshot.timestamp = payload_ts

        for key, value in payload.items():
            if key == "timestamp":
                continue

            if key in DEVICE_STATUS_FIELDS:
                _record_device_status(snapshot, device.device_id, key, value, payload_ts)
                continue

            if isinstance(value, dict) and key in FLATTENABLE_FIELDS:
                for sub_key, sub_value in value.items():
                    _maybe_store_metric(snapshot, sub_key, sub_value, device, payload_ts)
                continue

            if key not in ALLOWED_TOP_LEVEL_KEYS:
                continue

            if isinstance(value, (dict, list, tuple, set)):
                continue

            _maybe_store_metric(snapshot, key, value, device, payload_ts)

        new_alarm = _normalize_counter(payload.get("active_alarms"))
        prev_alarm = snapshot.alarms.get("active_alarms")
        if prev_alarm is None or new_alarm > prev_alarm:
            snapshot.alarms["active_alarms"] = new_alarm

        new_warning = _normalize_counter(payload.get("active_warnings"))
        prev_warning = snapshot.alarms.get("active_warnings")
        if prev_warning is None or new_warning > prev_warning:
            snapshot.alarms["active_warnings"] = new_warning

    return list(rooms.values())


def _maybe_store_metric(
    snapshot: RoomSnapshot,
    metric_key: str,
    metric_value: Any,
    device: DeviceInfo,
    timestamp: Optional[datetime],
):
    """Добавляет показание, если оно пригодно для отображения."""

    if metric_value is None:
        return

    if isinstance(metric_value, (dict, list, tuple, set)):
        return

    dtype_key = device.device_type.value
    allowed_keys = _DEVICE_METRIC_CACHE.setdefault(
        dtype_key,
        _build_allowed_keys_for_device(device),
    )
    if metric_key not in allowed_keys:
        allowed_keys = _DEVICE_METRIC_CACHE[dtype_key] = _build_allowed_keys_for_device(device)
        if metric_key not in allowed_keys:
            return

    # Всегда сохраняем показание в разрезе конкретного устройства
    record = MetricRecord(
        value=metric_value,
        device_id=device.device_id,
        device_type=device.device_type.value,
        timestamp=timestamp,
    )
    device_bucket = snapshot.device_metrics.setdefault(device.device_id, {})
    device_bucket[metric_key] = record

    meta_bucket = snapshot.metric_metadata.setdefault(device.device_id, {})
    if metric_key not in meta_bucket:
        meta = _get_metric_meta_for_device(device).get(metric_key)
        if meta:
            meta_bucket[metric_key] = meta

    current_record = snapshot.metrics.get(metric_key)
    should_replace = False
    if current_record is None:
        should_replace = True
    elif timestamp and current_record.timestamp and timestamp > current_record.timestamp:
        should_replace = True

    if should_replace:
        snapshot.metrics[metric_key] = record


def update_room_name(registry: DeviceRegistry, current_room: str, new_room: str) -> bool:
    """Обновляет название помещения и сохраняет конфиг устройств."""

    normalized_current = current_room or UNASSIGNED_ROOM_NAME
    normalized_new = (new_room or "").strip()
    if not normalized_new:
        raise ValueError("Название помещения не может быть пустым")

    changed = False
    for device in registry.get_devices(enabled_only=False):
        device_room = device.room or UNASSIGNED_ROOM_NAME
        if device_room == normalized_current:
            device.room = normalized_new
            changed = True

    if changed:
        registry.save_config()
        build_room_snapshots.clear()
        if "room_widget_keys" in st.session_state:
            st.session_state.pop("room_widget_keys")

    return changed


def _build_allowed_keys_for_device(device: DeviceInfo) -> set[str]:
    keys: set[str] = set()
    keys.update(get_device_metric_keys(device.device_type))
    return keys


def _get_metric_meta_for_device(device: DeviceInfo) -> Dict[str, MetricMeta]:
    dtype_key = device.device_type.value
    cached = _DEVICE_METADATA_CACHE.get(dtype_key)
    if cached is not None:
        return cached
    raw_meta = get_device_metric_metadata(device.device_type)
    converted: Dict[str, MetricMeta] = {}
    for key, info in raw_meta.items():
        converted[key] = MetricMeta(
            label=str(info.get("label")) if info.get("label") else None,
            unit=str(info.get("unit")) if info.get("unit") else None,
        )
    _DEVICE_METADATA_CACHE[dtype_key] = converted
    return converted
