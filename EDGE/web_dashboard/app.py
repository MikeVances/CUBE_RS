#!/usr/bin/env python3
"""
file: EDGE/web_dashboard/app.py
description: Операторский Streamlit-дашборд для наблюдения за помещениями и устройствами EDGE.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:  # streamlit_autorefresh входит в стандартный дистрибутив Streamlit
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # pragma: no cover - фоллбек, если компонент не установлен
    st_autorefresh = None

# Добавляем корень репозитория в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_dashboard.services.room_data import (
    DEVICE_STATUS_FIELDS,
    MetricRecord,
    RoomSnapshot,
    build_room_snapshots,
)
from web_dashboard.styles.dashboard_css import DASHBOARD_CSS

try:
    from core.device_registry import DeviceInfo, DeviceRegistry

    DEVICE_REGISTRY_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - optional dependency
    DEVICE_REGISTRY_AVAILABLE = False
    st.error(f"❌ Device Registry недоступен: {exc}")


@dataclass(frozen=True)
class MetricDescriptor:
    key: str
    label: str
    unit: str = ""
    category: str = "Общие"
    normal_range: Optional[Tuple[float, float]] = None


@dataclass
class FarmOverview:
    rooms_total: int = 0
    rooms_with_alarms: int = 0
    devices_total: int = 0
    devices_offline: int = 0
    avg_temp: Optional[float] = None
    active_alarms_total: int = 0
    last_update: Optional[datetime] = None


STATE_DIR = Path(__file__).resolve().parent / "state"
PREFERENCES_FILE = STATE_DIR / "user_preferences.json"


def _normalize_interval(value: Any) -> int:
    try:
        ivalue = int(value)
    except Exception:
        ivalue = 60
    if ivalue <= 0:
        ivalue = 60
    return max(60, min(600, ivalue))


def load_user_preferences() -> Dict[str, Any]:
    if not PREFERENCES_FILE.exists():
        return {}
    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}

    rooms_data: Dict[str, Dict[int, List[str]]] = {}
    for room_name, devices in data.get("rooms", {}).items():
        if not isinstance(devices, dict):
            continue
        room_devices: Dict[int, List[str]] = {}
        for device_id_raw, metrics in devices.items():
            try:
                device_id = int(device_id_raw)
            except Exception:
                continue
            if isinstance(metrics, list):
                room_devices[device_id] = [str(metric) for metric in metrics if isinstance(metric, str)]
        rooms_data[room_name] = room_devices

    auto_raw = data.get("auto_refresh", {})
    auto_block = {
        "enabled": bool(auto_raw.get("enabled", True)),
        "interval": _normalize_interval(auto_raw.get("interval", 60)),
    }

    return {"rooms": rooms_data, "auto_refresh": auto_block}


def save_user_preferences(payload: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(PREFERENCES_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Логировать не будем, чтобы не мешать UI
        pass


def _preferences_snapshot_from_state() -> Dict[str, Any]:
    return {
        "rooms": st.session_state.get("room_metric_prefs", {}),
        "auto_refresh": {
            "enabled": bool(st.session_state.get("auto_refresh_enabled", True)),
            "interval": _normalize_interval(st.session_state.get("auto_refresh_interval", 60)),
        },
    }


def _ensure_prefs_cache_initialized() -> None:
    if "_user_prefs_cache" not in st.session_state:
        snapshot = _preferences_snapshot_from_state()
        st.session_state["_user_prefs_cache"] = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)


def persist_user_preferences(force: bool = False) -> None:
    snapshot = _preferences_snapshot_from_state()
    serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    cache_value = st.session_state.get("_user_prefs_cache")
    if not force and cache_value == serialized:
        return
    save_user_preferences(snapshot)
    st.session_state["_user_prefs_cache"] = serialized


INITIAL_USER_PREFS = load_user_preferences()


METRIC_DESCRIPTORS: Dict[str, MetricDescriptor] = {
    "temp_inside": MetricDescriptor("temp_inside", "Температура", "°C", "Климат", (18, 28)),
    "temp_target": MetricDescriptor("temp_target", "Целевая t°", "°C", "Климат", (18, 28)),
    "temp_vent_activation": MetricDescriptor("temp_vent_activation", "t° вентиляции", "°C", "Климат"),
    "humidity": MetricDescriptor("humidity", "Влажность", "%", "Климат", (40, 70)),
    "co2": MetricDescriptor("co2", "CO₂", " ppm", "Климат"),
    "nh3": MetricDescriptor("nh3", "NH₃", " ppm", "Климат"),
    "pressure": MetricDescriptor("pressure", "Давление", " Pa", "Климат"),
    "ventilation_level": MetricDescriptor("ventilation_level", "Вентиляция", "%", "Вентиляция"),
    "ventilation_target": MetricDescriptor("ventilation_target", "Цель вентиляции", "%", "Вентиляция"),
    "ventilation_scheme": MetricDescriptor("ventilation_scheme", "Схема вентиляции", "", "Вентиляция"),
    "grv_base": MetricDescriptor("grv_base", "GRV базовый", "", "Вентиляция"),
    "grv_tunnel": MetricDescriptor("grv_tunnel", "GRV тоннель", "", "Вентиляция"),
    "damper": MetricDescriptor("damper", "Заслонка", "%", "Вентиляция"),
    "active_alarms": MetricDescriptor("active_alarms", "Активные тревоги", "", "Аварии"),
    "active_warnings": MetricDescriptor("active_warnings", "Предупреждения", "", "Аварии"),
    "registered_alarms": MetricDescriptor("registered_alarms", "История тревог", "", "Аварии"),
    "registered_warnings": MetricDescriptor("registered_warnings", "История предупреждений", "", "Аварии"),
    "day_counter": MetricDescriptor("day_counter", "Дней работы", "", "Общие"),
    "running_state": MetricDescriptor("running_state", "Состояние", "", "Приводы"),
    "set_frequency": MetricDescriptor("set_frequency", "Set frequency", " Hz", "Приводы"),
    "running_frequency": MetricDescriptor("running_frequency", "Run frequency", " Hz", "Приводы"),
    "running_speed": MetricDescriptor("running_speed", "Скорость", "", "Приводы"),
    "output_voltage": MetricDescriptor("output_voltage", "U выход", " V", "Электрика"),
    "output_current": MetricDescriptor("output_current", "I выход", " A", "Электрика"),
    "output_power": MetricDescriptor("output_power", "Мощность", " kW", "Электрика"),
    "motor_temperature": MetricDescriptor("motor_temperature", "t° двигателя", "°C", "Электрика"),
    "igbt_temperature": MetricDescriptor("igbt_temperature", "t° IGBT", "°C", "Электрика"),
    "fault_code": MetricDescriptor("fault_code", "Fault code", "", "Аварии"),
    "pressure_status": MetricDescriptor("pressure_status", "Статус давления", "", "Климат"),
    "humidity_status": MetricDescriptor("humidity_status", "Статус влажности", "", "Климат"),
    "co2_status": MetricDescriptor("co2_status", "Статус CO₂", "", "Климат"),
    "nh3_status": MetricDescriptor("nh3_status", "Статус NH₃", "", "Климат"),
    "connection_status": MetricDescriptor("connection_status", "Связь", "", "Общие"),
    "flame_level": MetricDescriptor("flame_level", "Уровень пламени", "%", "Обогрев"),
    "flame_present": MetricDescriptor("flame_present", "Пламя", "", "Обогрев"),
    "min_work_time": MetricDescriptor("min_work_time", "Мин. время работы", " с", "Обогрев"),
    "start_delay": MetricDescriptor("start_delay", "Задержка пуска", " с", "Обогрев"),
    "purge_duration": MetricDescriptor("purge_duration", "Продувка", " с", "Обогрев"),
    "operation_mode": MetricDescriptor("operation_mode", "Режим работы", "", "Обогрев"),
}

DEFAULT_ROOM_METRICS = ["temp_inside", "humidity", "co2", "pressure"]
ALWAYS_ON_METRICS: set[str] = set()
ALLOWED_METRIC_KEYS = set(METRIC_DESCRIPTORS.keys()) | ALWAYS_ON_METRICS
DEVICE_METRIC_LABEL_OVERRIDES: Dict[str, Dict[str, str]] = {
    "KUB-1112": {
        "temp_inside": "Температура корпуса",
        "temp_target": "Предельная t°",
    }
}

DEVICE_METRICS: Dict[str, List[str]] = {
    "KUB-1063": [
        "temp_inside",
        "temp_target",
        "humidity",
        "co2",
        "pressure",
        "ventilation_level",
        "ventilation_target",
    ],
    "KUB-1112": [
        "temp_inside",
        "temp_target",
        "pressure",
        "flame_level",
        "flame_present",
        "min_work_time",
        "start_delay",
        "purge_duration",
        "operation_mode",
    ],
    "VFD-INVERTER": [
        "running_state",
        "set_frequency",
        "running_frequency",
        "output_current",
        "output_voltage",
        "output_power",
        "igbt_temperature",
    ],
}

STATUS_OK_VALUES = {"ok", "online", "connected", "ready", "active", "normal"}
ADMIN_PIN_ENV = os.getenv("EDGE_DASHBOARD_ADMIN_PIN")


def get_admin_pin() -> Optional[str]:
    """Возвращает PIN администратора из окружения или secrets."""

    pin = ADMIN_PIN_ENV
    if pin:
        return pin
    try:
        return st.secrets.get("dashboard_admin_pin")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - secrets могут отсутствовать
        return None


def render_access_controls() -> bool:
    """Рисует блок управления ролью в сайдбаре и возвращает флаг админа."""

    pin = get_admin_pin()
    if not pin:
        st.info("Режим администратора активен по умолчанию (PIN не задан)")
        return True

    if st.session_state.get("is_admin"):
        st.success("Режим: администратор")
        if st.button("Выйти из админ-режима", key="logout_admin"):
            st.session_state["is_admin"] = False
            st.rerun()
    else:
        admin_input = st.text_input("PIN администратора", type="password", key="admin_pin_input")
        if st.button("Войти", key="login_admin"):
            if admin_input == pin:
                st.session_state["is_admin"] = True
                st.rerun()
            else:
                st.error("Неверный PIN")

    return st.session_state.get("is_admin", False)



@st.cache_resource(show_spinner=False)
def init_device_registry() -> DeviceRegistry:
    registry = DeviceRegistry()
    registry.load_devices_from_config()
    return registry


def apply_styles() -> None:
    """Добавляет CSS-тему."""
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)


def parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def is_status_ok(raw_status: Optional[str]) -> bool:
    if not raw_status:
        return False
    status = str(raw_status).lower()
    return status in STATUS_OK_VALUES


def format_metric_value(key: str, value: Any) -> str:
    if value is None:
        return "—"
    descriptor = METRIC_DESCRIPTORS.get(key)
    unit = descriptor.unit if descriptor else ""
    if isinstance(value, float):
        return f"{value:.1f}{unit}" if unit else f"{value:.1f}"
    if isinstance(value, int):
        return f"{value}{unit}" if unit else str(value)
    return f"{value}{unit}" if unit else str(value)


def metric_color(key: str, value: Any) -> str:
    descriptor = METRIC_DESCRIPTORS.get(key)
    if descriptor and descriptor.normal_range and isinstance(value, (int, float)):
        min_val, max_val = descriptor.normal_range
        return get_status_color(value, min_val, max_val)
    return "#58a6ff"


def default_metric_label(device_type: str, key: str) -> str:
    overrides = DEVICE_METRIC_LABEL_OVERRIDES.get(device_type)
    if overrides and key in overrides:
        return overrides[key]
    descriptor = METRIC_DESCRIPTORS.get(key, MetricDescriptor(key, key))
    return descriptor.label


def resolve_metric_label(room: RoomSnapshot, device: DeviceInfo, key: str) -> str:
    meta = getattr(room, "metric_metadata", {}).get(device.device_id, {}).get(key)
    if meta and meta.label:
        return meta.label
    return default_metric_label(device.device_type.value, key)


def get_status_color(value: float, min_val: float, max_val: float) -> str:
    if min_val <= value <= max_val:
        return "#28a745"
    midpoint = (min_val + max_val) / 2
    if value < min_val:
        return "#ffc107" if value >= midpoint else "#dc3545"
    return "#ffc107" if value <= midpoint else "#dc3545"


def collect_device_payloads(registry: DeviceRegistry) -> Dict[int, Dict[str, Any]]:
    payloads: Dict[int, Dict[str, Any]] = {}
    for device in registry.get_devices(enabled_only=True):
        try:
            payload = registry.get_device_data(device.device_id) or {}
        except Exception as exc:  # pragma: no cover - defensive
            st.warning(f"⚠️ Не удалось получить данные устройства {device.device_id}: {exc}")
            payload = {}
        payloads[device.device_id] = payload
    return payloads


def build_overview(rooms: List[RoomSnapshot], device_payloads: Dict[int, Dict[str, Any]]) -> FarmOverview:
    overview = FarmOverview()
    overview.rooms_total = len(rooms)
    overview.rooms_with_alarms = sum(1 for room in rooms if room.alarms.get("active_alarms", 0))
    overview.devices_total = len(device_payloads)

    alarm_total = 0
    timestamps: List[datetime] = []
    temps: List[float] = []

    for room in rooms:
        alarm_total += room.alarms.get("active_alarms", 0)
        if room.timestamp:
            timestamps.append(room.timestamp)
        metric = room.metrics.get("temp_inside")
        if metric and isinstance(metric.value, (int, float)):
            temps.append(float(metric.value))

    for payload in device_payloads.values():
        ts = parse_timestamp(payload.get("timestamp"))
        if ts:
            timestamps.append(ts)
        status = payload.get("connection_status") or payload.get("status")
        if not is_status_ok(status):
            overview.devices_offline += 1

    overview.active_alarms_total = alarm_total
    overview.avg_temp = sum(temps) / len(temps) if temps else None
    overview.last_update = max(timestamps) if timestamps else None
    return overview


def render_overview(overview: FarmOverview) -> None:
    st.subheader("🏭 Обзор фермы")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Помещения (тревоги)</h4>
                    <p>{overview.rooms_with_alarms}/{overview.rooms_total}</p>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Устройств оффлайн</h4>
                    <p>{overview.devices_offline}</p>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with col3:
        avg_temp = "—" if overview.avg_temp is None else f"{overview.avg_temp:.1f}°C"
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Средняя температура</h4>
                    <p>{avg_temp}</p>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with col4:
        updated = overview.last_update.strftime("%d.%m %H:%M:%S") if overview.last_update else "—"
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Последнее обновление</h4>
                    <p>{updated}</p>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )


def get_room_metric_preferences(room: RoomSnapshot) -> Dict[int, List[str]]:
    prefs = st.session_state.setdefault("room_metric_prefs", {})
    room_pref: Dict[int, List[str]] = prefs.setdefault(room.room, {})

    valid_device_ids = {device.device_id for device in room.devices}
    for device_id in list(room_pref.keys()):
        if device_id not in valid_device_ids:
            room_pref.pop(device_id)

    for device in room.devices:
        if device.device_id not in room_pref:
            defaults = DEVICE_METRICS.get(device.device_type.value) or DEFAULT_ROOM_METRICS
            room_pref[device.device_id] = [key for key in defaults if key not in ALWAYS_ON_METRICS]

        filtered = [
            key
            for key in room_pref[device.device_id]
            if key in ALLOWED_METRIC_KEYS
        ]
        room_pref[device.device_id] = filtered

    return {device_id: list(keys) for device_id, keys in room_pref.items()}


def update_room_metric_preferences(room: RoomSnapshot, selection: Dict[int, List[str]]) -> None:
    prefs = st.session_state.setdefault("room_metric_prefs", {})
    prefs[room.room] = selection
    persist_user_preferences()


def get_room_device_metrics(room: RoomSnapshot) -> Dict[int, Dict[str, MetricRecord]]:
    if getattr(room, "device_metrics", None):
        filtered: Dict[int, Dict[str, MetricRecord]] = {}
        for device_id, metrics in room.device_metrics.items():
            filtered[device_id] = {
                key: record
                for key, record in metrics.items()
                if key in ALLOWED_METRIC_KEYS
            }
        return filtered

    # Fallback: собираем из плоского snapshot.metrics
    grouped: Dict[int, Dict[str, MetricRecord]] = {}
    for key, record in room.metrics.items():
        if not record or record.device_id is None:
            continue
        if key not in ALLOWED_METRIC_KEYS:
            continue
        grouped.setdefault(record.device_id, {})[key] = record
    return grouped


def render_room_metrics(
    room: RoomSnapshot,
    preferences: Dict[int, List[str]],
    device_payloads: Dict[int, Dict[str, Any]],
    device_metric_records: Dict[int, Dict[str, MetricRecord]],
) -> None:
    if not room.devices:
        st.info("Нет активных устройств в помещении")
        return

    device_statuses = getattr(room, "device_statuses", {})

    for device in room.devices:
        payload = device_payloads.get(device.device_id, {})
        device_snapshot = device_metric_records.get(device.device_id, {})
        selected_keys = preferences.get(device.device_id, [])
        status = device_statuses.get(device.device_id)

        st.markdown(f"#### {device.name} · {device.device_type.value}")

        cards_html: List[str] = []

        alarm_record = device_snapshot.get("active_alarms")
        alarm_value: Any = None
        if status and status.active_alarms is not None:
            alarm_value = status.active_alarms
        elif payload.get("active_alarms") is not None:
            alarm_value = payload.get("active_alarms")
        elif alarm_record is not None:
            alarm_value = alarm_record.value
        try:
            alarm_value_int = int(alarm_value or 0)
        except (TypeError, ValueError):
            alarm_value_int = 0

        fault_record = device_snapshot.get("fault_code")
        fault_code = None
        if status and status.fault_code is not None:
            fault_code = status.fault_code
        elif payload.get("fault_code") is not None:
            fault_code = payload.get("fault_code")
        elif fault_record is not None:
            fault_code = fault_record.value

        alarm_color = "#dc3545" if alarm_value_int else "#238636"
        alarm_text = f"{alarm_value_int} активны" if alarm_value_int else "Норма"
        alarm_details: List[str] = []
        if status and status.alarms:
            alarm_details.append(str(status.alarms[0]))
        if status and status.warnings:
            alarm_details.append(str(status.warnings[0]))
        fault_text = f"Fault: {fault_code}" if fault_code not in (None, 0, "0", "OK", "") else ""
        if fault_text:
            alarm_details.append(fault_text)
        detail_html = "<br/>".join(alarm_details)
        cards_html.append(
            dedent(
                f"""
                <div class="metric-card">
                    <small>Аварии</small>
                    <h4 style="margin: 6px 0; color:{alarm_color};">{alarm_text}</h4>
                    <small>{detail_html}</small>
                </div>
                """
            )
        )

        if not selected_keys:
            cards_html.append(
                dedent(
                    """
                    <div class="metric-card">
                        <small>Нет выбранных метрик</small>
                        <h4 style="margin: 6px 0;">—</h4>
                    </div>
                    """
                )
            )
        else:
            for key in selected_keys:
                descriptor = METRIC_DESCRIPTORS.get(key, MetricDescriptor(key, key))
                label = resolve_metric_label(room, device, key)
                value = payload.get(key)
                if value is None:
                    record = device_snapshot.get(key)
                    value = record.value if record else None
                cards_html.append(
                    dedent(
                        f"""
                        <div class="metric-card">
                            <small>{label}</small>
                            <h4 style=\"margin: 6px 0; color:{metric_color(key, value)};\">{format_metric_value(key, value)}</h4>
                        </div>
                        """
                    )
                )

        st.markdown(f"<div class='metric-grid'>{''.join(cards_html)}</div>", unsafe_allow_html=True)


def render_device_cards(room: RoomSnapshot, device_payloads: Dict[int, Dict[str, Any]]) -> None:
    if not room.devices:
        st.info("Нет активных устройств")
        return

    device_statuses = getattr(room, "device_statuses", {})

    for device in room.devices:
        payload = device_payloads.get(device.device_id, {})
        status_obj = device_statuses.get(device.device_id)
        status = (
            (status_obj.connection_status if status_obj else None)
            or (status_obj.status if status_obj else None)
            or payload.get("connection_status")
            or payload.get("status")
            or "unknown"
        )
        alarms_value = None
        if status_obj and status_obj.active_alarms is not None:
            alarms_value = status_obj.active_alarms
        elif payload.get("active_alarms") is not None:
            alarms_value = payload.get("active_alarms")
        try:
            alarms_count = int(alarms_value or 0)
        except (TypeError, ValueError):
            alarms_count = 0
        status_ok = is_status_ok(status) and alarms_count == 0
        pill_color = "#238636" if status_ok else "#dc3545"
        updated = parse_timestamp(payload.get("timestamp"))
        updated_str = updated.strftime("%d.%m %H:%M:%S") if updated else "—"

        extra_status = ""
        if status_obj and status_obj.alarms:
            extra_status = status_obj.alarms[0]
        elif status_obj and status_obj.warnings:
            extra_status = status_obj.warnings[0]

        st.markdown(
            dedent(
                f"""
                <div class="device-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <strong>{device.name}</strong><br/>
                            <small>ID {device.device_id} · Slave {device.slave_id} · {device.device_type.value}</small><br/>
                            <small>Обновлено: {updated_str}</small><br/>
                            <small>{extra_status}</small>
                        </div>
                        <div class="status-pill" style="background-color:{pill_color}22; color:{pill_color};">
                            <span>{'OK' if status_ok else 'Проблема'}</span>
                        </div>
                    </div>
                """
            ),
            unsafe_allow_html=True,
        )

        metric_keys = DEVICE_METRICS.get(device.device_type.value)
        if not metric_keys:
            metric_keys = list(key for key in payload.keys() if key in METRIC_DESCRIPTORS)
        if not metric_keys:
            st.write("Нет описанных метрик для отображения")
            st.markdown("</div>", unsafe_allow_html=True)
            continue

        metrics_html = []
        for key in metric_keys:
            value = payload.get(key)
            label = resolve_metric_label(room, device, key)
            metrics_html.append(
                dedent(
                    f"""
                    <div class="metric-card">
                        <small>{label}</small>
                        <h4 style="margin:6px 0;">{format_metric_value(key, value)}</h4>
                    </div>
                    """
                )
            )
        st.markdown(f"<div class='metric-grid'>{''.join(metrics_html)}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def render_room_settings(
    room: RoomSnapshot,
    preferences: Dict[int, List[str]],
    device_payloads: Dict[int, Dict[str, Any]],
    device_metric_records: Dict[int, Dict[str, MetricRecord]],
) -> Dict[int, List[str]]:
    st.write("Отметьте показатели для каждого устройства. Аварии отображаются всегда и не требуют настройки.")

    updated: Dict[int, List[str]] = {device.device_id: preferences.get(device.device_id, []) for device in room.devices}
    for device in room.devices:
        payload = device_payloads.get(device.device_id, {})
        device_snapshot = device_metric_records.get(device.device_id, {})
        available_keys = set(DEVICE_METRICS.get(device.device_type.value, []))
        available_keys |= {key for key in payload.keys() if key in METRIC_DESCRIPTORS}
        available_keys |= {key for key in device_snapshot.keys() if key in METRIC_DESCRIPTORS}
        available_keys -= ALWAYS_ON_METRICS
        available_keys -= DEVICE_STATUS_FIELDS

        if not available_keys:
            continue

        current_selection = preferences.get(device.device_id, [])
        with st.expander(f"{device.name} · {device.device_type.value}", expanded=False):
            device_selection: List[str] = []
            for key in sorted(available_keys):
                descriptor = METRIC_DESCRIPTORS.get(key, MetricDescriptor(key, key))
                checkbox_key = f"pref::{room.room}::{device.device_id}::{key}"
                if checkbox_key not in st.session_state:
                    st.session_state[checkbox_key] = key in current_selection
                checked = st.checkbox(descriptor.label, key=checkbox_key)
                if checked:
                    device_selection.append(key)

            if not device_selection:
                device_selection = current_selection

            updated[device.device_id] = device_selection

    if all((not metrics) for metrics in updated.values()):
        st.info("Нет устройств с настраиваемыми параметрами")

    return updated


def render_room_panel(room: RoomSnapshot, device_payloads: Dict[int, Dict[str, Any]]) -> None:
    alarms = room.alarms.get("active_alarms", 0)
    warnings = room.alarms.get("active_warnings", 0)
    badge_color = "#238636" if alarms == 0 else "#dc3545"
    badge_text = "Норма" if alarms == 0 else f"Тревог: {alarms}"
    subtitle = room.location or "—"
    updated = room.timestamp.strftime("%d.%m %H:%M:%S") if room.timestamp else "—"

    st.markdown(
        dedent(
            f"""
            <div class="room-panel">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h3 style="margin-bottom:4px;">{room.room}</h3>
                        <small>{subtitle}</small><br/>
                        <small>Обновлено: {updated}</small>
                    </div>
                    <div class="status-pill" style="background-color:{badge_color}22; color:{badge_color};">
                        <span>{badge_text}</span>
                    </div>
                </div>
            """
        ),
        unsafe_allow_html=True,
    )

    preferences = get_room_metric_preferences(room)
    device_metric_records = get_room_device_metrics(room)

    overview_tab, devices_tab, settings_tab = st.tabs(["Обзор", "Устройства", "Настройки"])

    with overview_tab:
        render_room_metrics(room, preferences, device_payloads, device_metric_records)
        if warnings:
            st.warning(f"Предупреждений: {warnings}")

    with devices_tab:
        render_device_cards(room, device_payloads)

    with settings_tab:
        updated = render_room_settings(room, preferences, device_payloads, device_metric_records)
        if updated:
            update_room_metric_preferences(room, updated)

    st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard_tab(rooms: List[RoomSnapshot], device_payloads: Dict[int, Dict[str, Any]]) -> None:
    if not rooms:
        st.info("Нет активных помещений. Заполните config/devices.yaml")
        return

    overview = build_overview(rooms, device_payloads)
    render_overview(overview)

    st.subheader("🏢 Помещения")
    for room in rooms:
        render_room_panel(room, device_payloads)


def render_configuration_tab(registry: DeviceRegistry) -> None:
    st.subheader("⚙️ Конфигурация фермы")
    devices = registry.get_devices(enabled_only=False)
    if not devices:
        st.info("Нет устройств для конфигурации")
        return

    rows = [
        {
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type.value,
            "room": device.room or "",
            "location": device.location or "",
            "enabled": device.enabled,
        }
        for device in devices
    ]

    editor = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "device_id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Имя устройства", disabled=True),
            "device_type": st.column_config.TextColumn("Тип", disabled=True),
            "room": st.column_config.TextColumn("Помещение"),
            "location": st.column_config.TextColumn("Локация"),
            "enabled": st.column_config.CheckboxColumn("Активно"),
        },
        key="farm_config_editor",
    )

    st.caption("Редактируйте помещение, локацию и включённость устройств. ID/имя изменяются через отдельные инструменты.")

    if st.button("💾 Сохранить конфигурацию", type="primary"):
        edited_records = {int(row["device_id"]): row for row in editor.to_dict("records")}
        changed = False
        for device in devices:
            row = edited_records.get(device.device_id)
            if not row:
                continue
            new_room = (row.get("room") or "").strip() or None
            new_loc = (row.get("location") or "").strip() or None
            new_enabled = bool(row.get("enabled"))

            if device.room != new_room:
                device.room = new_room
                changed = True
            if device.location != new_loc:
                device.location = new_loc
                changed = True
            if device.enabled != new_enabled:
                device.enabled = new_enabled
                changed = True

        if changed:
            registry.save_config()
            build_room_snapshots.clear()
            st.success("Конфигурация сохранена")
            st.rerun()
        else:
            st.info("Изменений нет")


def load_data(registry: DeviceRegistry) -> Tuple[List[RoomSnapshot], Dict[int, Dict[str, Any]]]:
    rooms = build_room_snapshots(registry)
    payloads = collect_device_payloads(registry)
    return rooms, payloads


def main() -> None:
    st.set_page_config(page_title="CUBE_RS EDGE Dashboard", layout="wide")
    apply_styles()

    if not DEVICE_REGISTRY_AVAILABLE:
        st.stop()

    try:
        registry = init_device_registry()
    except Exception as exc:
        st.error(f"Не удалось инициализировать Device Registry: {exc}")
        st.stop()

    # Значения по умолчанию загружаем из сохранённых настроек
    st.session_state.setdefault("room_metric_prefs", INITIAL_USER_PREFS.get("rooms", {}))
    st.session_state.setdefault(
        "auto_refresh_enabled",
        INITIAL_USER_PREFS.get("auto_refresh", {}).get("enabled", True),
    )
    st.session_state.setdefault(
        "auto_refresh_interval",
        INITIAL_USER_PREFS.get("auto_refresh", {}).get("interval", 60),
    )
    st.session_state["auto_refresh_interval"] = _normalize_interval(
        st.session_state.get("auto_refresh_interval", 60)
    )
    _ensure_prefs_cache_initialized()

    with st.sidebar:
        st.header("🔐 Доступ")
        is_admin = render_access_controls()
        st.header("⚙️ Обновление")
        auto_refresh_enabled = st.checkbox(
            "Автообновление",
            key="auto_refresh_enabled",
        )
        auto_refresh_interval = (
            st.slider(
                "Интервал, мин",
                min_value=1,
                max_value=10,
                value=max(1, min(10, st.session_state["auto_refresh_interval"] // 60)),
                key="auto_refresh_interval_minutes",
                disabled=not auto_refresh_enabled,
            )
            * 60
        )
        st.session_state["auto_refresh_interval"] = auto_refresh_interval
        persist_user_preferences()
        if auto_refresh_enabled and st_autorefresh is None:
            st.warning("Автообновление недоступно: отсутствует модуль streamlit_autorefresh")
        refresh_now = st.button("Обновить сейчас")
        st.header("ℹ️ Справка")
        st.info("Состав устройств и помещений задаётся в config/devices.yaml")

    if refresh_now:
        st.rerun()

    if st.session_state.get("auto_refresh_enabled") and st_autorefresh is not None:
        st_autorefresh(
            interval=_normalize_interval(st.session_state.get("auto_refresh_interval", 60)) * 1000,
            key="edge_dashboard_autorefresh",
        )

    try:
        rooms, device_payloads = load_data(registry)
    except Exception as exc:
        st.error(f"Не удалось загрузить данные: {exc}")
        return

    tab_titles = ["Дашборд"] + (["Конфигурация"] if is_admin else [])
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        render_dashboard_tab(rooms, device_payloads)

    if is_admin and len(tabs) > 1:
        with tabs[1]:
            render_configuration_tab(registry)


if __name__ == "__main__":
    main()
