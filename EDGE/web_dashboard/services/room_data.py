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

UNASSIGNED_ROOM_NAME = "Без помещения"
FLATTENABLE_FIELDS = {"registers", "metrics", "values"}


@dataclass
class MetricRecord:
    """Представление отдельного измерения внутри помещения."""

    value: Any
    device_id: Optional[int] = None
    device_type: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class RoomSnapshot:
    """Снимок состояния помещения с агрегированными показателями."""

    room: str
    location: str
    devices: List[DeviceInfo] = field(default_factory=list)
    metrics: Dict[str, MetricRecord] = field(default_factory=dict)
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
            if key in {"timestamp"}:
                continue

            if isinstance(value, dict) and key in FLATTENABLE_FIELDS:
                for sub_key, sub_value in value.items():
                    _maybe_store_metric(snapshot, sub_key, sub_value, device, payload_ts)
                continue

            if isinstance(value, (dict, list, tuple, set)):
                continue

            _maybe_store_metric(snapshot, key, value, device, payload_ts)

        snapshot.alarms["active_alarms"] = max(
            snapshot.alarms.get("active_alarms", 0),
            _normalize_counter(payload.get("active_alarms")),
        )
        snapshot.alarms["active_warnings"] = max(
            snapshot.alarms.get("active_warnings", 0),
            _normalize_counter(payload.get("active_warnings")),
        )

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

    current_record = snapshot.metrics.get(metric_key)
    should_replace = False
    if current_record is None:
        should_replace = True
    elif timestamp and current_record.timestamp and timestamp > current_record.timestamp:
        should_replace = True

    if should_replace:
        snapshot.metrics[metric_key] = MetricRecord(
            value=metric_value,
            device_id=device.device_id,
            device_type=device.device_type.value,
            timestamp=timestamp,
        )


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
