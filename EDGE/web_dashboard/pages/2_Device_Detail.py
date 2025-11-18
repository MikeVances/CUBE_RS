#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from typing import Optional

import streamlit as st
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.device_registry import DeviceRegistry, DeviceInfo


@st.cache_resource(show_spinner=False)
def get_registry() -> DeviceRegistry:
    reg = DeviceRegistry()
    reg.load_devices_from_config()
    return reg


@st.cache_data(ttl=2.0, show_spinner=False)
def fetch_device(device_id: int) -> Optional[DeviceInfo]:
    return get_registry().get_device(device_id)


@st.cache_data(ttl=2.0, show_spinner=False)
def fetch_data(device_id: int) -> dict:
    data = get_registry().get_device_data(device_id) or {}
    if data and "timestamp" not in data:
        data["timestamp"] = datetime.now().isoformat()
    return data


def metric_card(title: str, value_str: str, color: str = "#58a6ff"):
    st.markdown(
        f"""
        <div style=\"background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {color};\">
            <h4 style=\"margin: 0; color: #e6edf3;\">{title}</h4>
            <h2 style=\"margin: 8px 0; color: {color};\">{value_str}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="Device Detail", layout="wide")
    st.title("🔍 Device Detail")

    qp = st.query_params
    selected_id = qp.get("device_id")
    if isinstance(selected_id, list):
        selected_id = selected_id[0]
    if selected_id is None:
        selected_id = st.session_state.get("selected_device_id")
    if selected_id is None:
        st.info("Выберите устройство на странице ‘Devices’ (или укажите ID ниже)")
        selected_id = st.number_input("Device ID", min_value=1, step=1)
        if st.button("Загрузить"):
            st.query_params["device_id"] = str(int(selected_id))
            st.rerun()
        return

    try:
        device_id = int(selected_id)
    except Exception:
        st.error(f"Некорректный device_id: {selected_id}")
        return

    dev = fetch_device(device_id)
    if not dev:
        st.error(f"Устройство ID={device_id} не найдено")
        return

    # Header
    info_md = f"""
**ID**: {dev.device_id}  
**Slave**: {dev.slave_id}  
**Тип**: {dev.device_type.value}  
**Помещение**: {dev.room or '—'}  
**Локация**: {dev.location or '—'}
"""
    st.markdown(info_md)

    data = fetch_data(device_id)
    st.markdown("---")
    st.subheader("🎯 Показатели")
    c1, c2, c3, c4 = st.columns(4)

    if dev.device_type.value == "KUB-1063":
        with c1:
            metric_card("Температура", f"{(data.get('temp_inside') or 0)/1:.1f}°C")
        with c2:
            metric_card("Целевая", f"{(data.get('temp_target') or 0)/1:.1f}°C")
        with c3:
            hum = data.get("humidity")
            metric_card("Влажность", f"{hum/10:.1f}%" if hum is not None else "N/A")
        with c4:
            press = data.get("pressure")
            metric_card("Давление", f"{press/10:.1f} Pa" if press is not None else "N/A")
    else:
        with c1:
            metric_card("Set freq", f"{(data.get('set_frequency') or 0):.1f} Hz")
        with c2:
            metric_card("Run freq", f"{(data.get('running_frequency') or 0):.1f} Hz")
        with c3:
            metric_card("Ток", f"{(data.get('output_current') or 0):.1f} A")
        with c4:
            metric_card("IGBT", f"{(data.get('igbt_temperature') or 0):.0f}°C")

    st.markdown("---")
    st.subheader("📚 Регистры")
    if data:
        rows = []
        for k, v in data.items():
            rows.append({"Параметр": k, "Значение": v})
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("Нет данных для отображения (ожидайте опрос)")


if __name__ == "__main__":
    main()
