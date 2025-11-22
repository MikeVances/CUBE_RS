#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from typing import List

import streamlit as st
import pandas as pd

# Ensure project root on path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.device_registry import DeviceRegistry, DeviceInfo, DeviceType


@st.cache_resource(show_spinner=False)
def get_registry() -> DeviceRegistry:
    reg = DeviceRegistry()
    reg.load_devices_from_config()
    return reg


@st.cache_data(ttl=2.0, show_spinner=False)
def fetch_device_data(device_id: int) -> dict:
    reg = get_registry()
    data = reg.get_device_data(device_id) or {}
    if data and "timestamp" not in data:
        data["timestamp"] = datetime.now().isoformat()
    return data


def main():
    st.set_page_config(page_title="EDGE Devices", layout="wide", initial_sidebar_state="expanded")
    st.title("🗂️ Устройства (Devices)")

    reg = get_registry()
    devices: List[DeviceInfo] = reg.get_devices(enabled_only=True)

    # Filters
    rooms = sorted({d.room or "—" for d in devices})
    types = sorted({d.device_type.value for d in devices})

    c1, c2, c3 = st.columns(3)
    with c1:
        room_filter = st.multiselect("Помещение (room)", rooms, default=rooms)
    with c2:
        type_filter = st.multiselect("Тип устройства", types, default=types)
    with c3:
        search = st.text_input("Поиск по имени/ID/slave", "").strip().lower()

    # Filtered list
    filtered: List[DeviceInfo] = []
    for d in devices:
        if (d.room or "—") not in room_filter:
            continue
        if d.device_type.value not in type_filter:
            continue
        if search:
            hay = f"{d.device_id} {d.slave_id} {d.name} {d.location or ''}".lower()
            if search not in hay:
                continue
        filtered.append(d)

    # Build table rows
    rows = []
    for d in filtered:
        data = fetch_device_data(d.device_id)
        status = data.get("connection_status") or data.get("status") or "unknown"
        rows.append(
            {
                "ID": d.device_id,
                "Slave": d.slave_id,
                "Имя": d.name,
                "Тип": d.device_type.value,
                "Помещение": d.room or "—",
                "Локация": d.location or "—",
                "Статус": status,
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch")

    st.markdown("---")
    st.subheader("🔎 Открыть детали")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        selected_id = st.number_input("Device ID", min_value=1, step=1)
        if st.button("Открыть детализацию"):
            st.session_state["selected_device_id"] = int(selected_id)
            st.success("Перейдите на страницу ‘Device Detail’ в меню слева")
            st.query_params["device_id"] = str(int(selected_id))


if __name__ == "__main__":
    main()
