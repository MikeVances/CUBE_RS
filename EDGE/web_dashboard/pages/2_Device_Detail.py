#!/usr/bin/env python3
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.device_registry import DeviceRegistry, DeviceInfo, DeviceType
from core.device_adapters.factory import get_device_metric_metadata


@dataclass(frozen=True)
class DeviceMetricConfig:
    key: str
    label: str
    unit: str = ""
    scale: float = 1.0
    format_spec: Optional[str] = ".1f"



@st.cache_resource(show_spinner=False)
def _build_metric_configs(device_type_value: str) -> List[DeviceMetricConfig]:
    try:
        dtype = DeviceType(device_type_value)
    except Exception:
        return []
    metadata = get_device_metric_metadata(dtype)
    if not metadata:
        return []
    configs: List[DeviceMetricConfig] = []
    for key in sorted(metadata.keys()):
        meta = metadata.get(key) or {}
        label = meta.get("label") or key
        unit = meta.get("unit") or ""
        configs.append(DeviceMetricConfig(key, label, unit))
    return configs


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


def format_metric_value(data: dict, cfg: DeviceMetricConfig) -> str:
    value = data.get(cfg.key)
    if value is None:
        return "N/A"

    if isinstance(value, (int, float)):
        scaled = value / cfg.scale if cfg.scale else value
        if cfg.format_spec:
            formatted = f"{scaled:{cfg.format_spec}}"
        else:
            formatted = f"{scaled}"
    else:
        formatted = str(value)

    return f"{formatted}{cfg.unit}" if cfg.unit else formatted


def pick_metric_configs(device_id: int, device_type: str) -> List[DeviceMetricConfig]:
    configs = _build_metric_configs(device_type)
    if not configs:
        return []

    state_key = f"device_detail_metrics::{device_id}"
    selected_keys = st.session_state.get(state_key)
    if not selected_keys:
        selected_keys = [cfg.key for cfg in configs[:4]] or [cfg.key for cfg in configs]
        st.session_state[state_key] = selected_keys

    updated_selection: List[str] = []
    with st.expander("⚙️ Настройка показателей", expanded=False):
        st.caption("Отметьте показатели, которые должны отображаться в карточках.")
        for cfg in configs:
            checkbox_key = f"{state_key}::{cfg.key}"
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = cfg.key in selected_keys
            checked = st.checkbox(cfg.label, key=checkbox_key)
            if checked:
                updated_selection.append(cfg.key)

    if updated_selection:
        st.session_state[state_key] = updated_selection
    elif not st.session_state[state_key]:
        st.session_state[state_key] = selected_keys

    selected = [cfg for cfg in configs if cfg.key in st.session_state[state_key]]
    return selected


def render_metric_cards(data: dict, configs: List[DeviceMetricConfig]) -> None:
    if not configs:
        st.info("Для данного типа устройства нет описанных показателей")
        return

    cols_per_row = 4
    selected = configs
    for start in range(0, len(selected), cols_per_row):
        row_configs = selected[start : start + cols_per_row]
        columns = st.columns(len(row_configs))
        for column, cfg in zip(columns, row_configs):
            with column:
                metric_card(cfg.label, format_metric_value(data, cfg))


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
    selected_configs = pick_metric_configs(dev.device_id, dev.device_type.value)
    if selected_configs:
        render_metric_cards(data, selected_configs)
    else:
        st.info("Добавьте хотя бы один показатель во вкладке настроек выше")

    st.markdown("---")
    st.subheader("📚 Регистры")
    if data:
        rows = []
        for k, v in data.items():
            rows.append({"Параметр": k, "Значение": v})
        st.dataframe(pd.DataFrame(rows), width="stretch")
    else:
        st.info("Нет данных для отображения (ожидайте опрос)")


if __name__ == "__main__":
    main()
