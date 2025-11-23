"""
file: services/room_data.py
description: Потоковый адаптер для room_snapshot_service с Streamlit-кэшем и UI-хелперами.
author: Streamlit Analytics Engineer GPT
"""

from __future__ import annotations

from typing import List

import streamlit as st

from core.device_registry import DeviceRegistry
from core.room_snapshot_service import (
    DEVICE_STATUS_FIELDS,
    MetricRecord,
    RoomSnapshot,
    UNASSIGNED_ROOM_NAME,
    build_room_snapshots as _build_room_snapshots,
)


@st.cache_data(ttl=2.0, show_spinner=False, hash_funcs={DeviceRegistry: lambda _: "device_registry"})
def build_room_snapshots(registry: DeviceRegistry) -> List[RoomSnapshot]:
    """Streamlit-кэшированная обёртка поверх core.room_snapshot_service."""
    return _build_room_snapshots(registry)


def update_room_name(registry: DeviceRegistry, current_room: str, new_room: str) -> bool:
    """Обновляет название помещения и инвалидирует Streamlit-кэш."""

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
