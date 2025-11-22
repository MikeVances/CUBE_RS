#!/usr/bin/env python3
"""
file: EDGE/web_dashboard/app.py
description: Операторский Streamlit-дашборд для наблюдения за помещениями и устройствами EDGE.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import html
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    UNASSIGNED_ROOM_NAME,
    build_room_snapshots,
)
from web_dashboard.styles.dashboard_css import DASHBOARD_CSS
from modbus.modbus_storage import DB_FILE

try:
    from core.device_registry import DeviceInfo, DeviceRegistry, DeviceType
    from core.device_adapters.catalog import DEVICE_DEFINITIONS
    from core.device_adapters.factory import get_device_metric_metadata

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
    rooms_unassigned: int = 0


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


BASE_METRIC_DESCRIPTORS: Dict[str, MetricDescriptor] = {
    "connection_status": MetricDescriptor("connection_status", "Связь", "", "Общие"),
    "active_alarms": MetricDescriptor("active_alarms", "Активные тревоги", "", "Аварии"),
    "active_warnings": MetricDescriptor("active_warnings", "Предупреждения", "", "Аварии"),
    "registered_alarms": MetricDescriptor("registered_alarms", "История тревог", "", "Аварии"),
    "registered_warnings": MetricDescriptor("registered_warnings", "История предупреждений", "", "Аварии"),
    "fault_code": MetricDescriptor("fault_code", "Fault code", "", "Аварии"),
    "day_counter": MetricDescriptor("day_counter", "Дней работы", "", "Общие"),
}


def build_metric_descriptors() -> Dict[str, MetricDescriptor]:
    descriptors = dict(BASE_METRIC_DESCRIPTORS)
    for definition in DEVICE_DEFINITIONS:
        try:
            dtype = DeviceType(definition.type)
        except Exception:
            continue
        metadata = get_device_metric_metadata(dtype)
        for key, meta in metadata.items():
            if key in descriptors:
                continue
            label = meta.get("label") or key
            unit = meta.get("unit") or ""
            descriptors[key] = MetricDescriptor(key, label, unit)
    return descriptors


METRIC_DESCRIPTORS = build_metric_descriptors()
DEFAULT_ROOM_METRICS = ["temp_inside", "humidity", "co2", "pressure"]
ALWAYS_ON_METRICS: set[str] = set()
ALLOWED_METRIC_KEYS = set(METRIC_DESCRIPTORS.keys()) | ALWAYS_ON_METRICS
DEVICE_METRIC_LABEL_OVERRIDES: Dict[str, Dict[str, str]] = {
    "KUB-1112": {
        "temp_inside": "Температура корпуса",
        "temp_target": "Предельная t°",
    }
}

def build_device_metrics_map() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for definition in DEVICE_DEFINITIONS:
        try:
            dtype = DeviceType(definition.type)
        except Exception:
            continue
        metadata = get_device_metric_metadata(dtype)
        mapping[definition.type] = list(metadata.keys())
    return mapping


DEVICE_METRICS = build_device_metrics_map()

STATUS_OK_VALUES = {"ok", "online", "connected", "ready", "active", "normal"}
STATUS_HUMAN_READABLE = {
    "offline": "Нет связи",
    "disconnected": "Нет связи",
    "error": "Ошибка",
    "fault": "Авария",
    "stop": "Остановлено",
}
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


def humanize_status(raw_status: Optional[str]) -> Optional[str]:
    if not raw_status:
        return None
    status_lower = str(raw_status).lower()
    return STATUS_HUMAN_READABLE.get(status_lower, raw_status)


def normalize_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_fault(fault_value: Any) -> Optional[str]:
    if fault_value is None:
        return None
    text = str(fault_value).strip()
    if not text:
        return None
    if text.lower() in {"0", "none", "no_fault", "ok"}:
        return None
    return text


def escape_html(value: str) -> str:
    return html.escape(value, quote=False)


def collect_problem_reasons(
    *,
    status_obj: Optional[Any],
    payload: Dict[str, Any],
    human_status: Optional[str],
    alarms_count: int,
) -> List[str]:
    reasons: List[str] = []
    connection_status = None
    if status_obj and getattr(status_obj, "connection_status", None):
        connection_status = status_obj.connection_status
    elif payload.get("connection_status"):
        connection_status = payload.get("connection_status")

    if connection_status and not is_status_ok(connection_status):
        reasons.append(f"Связь: {humanize_status(connection_status) or connection_status}")

    if human_status and human_status.lower() not in STATUS_OK_VALUES:
        reasons.append(f"Состояние: {human_status}")

    last_error = None
    if status_obj and getattr(status_obj, "last_error", None):
        last_error = status_obj.last_error
    elif payload.get("last_error"):
        last_error = payload.get("last_error")
    if last_error:
        text = normalize_fault(last_error)
        if text:
            reasons.append(text)

    if alarms_count:
        if status_obj and getattr(status_obj, "alarms", None):
            reasons.extend(status_obj.alarms[:3])
        else:
            reasons.append(f"Активных тревог: {alarms_count}")
    elif status_obj and getattr(status_obj, "warnings", None):
        warnings = status_obj.warnings[:2]
        if warnings:
            reasons.extend([f"Предупреждение: {msg}" for msg in warnings])

    fault_code = None
    if status_obj and getattr(status_obj, "fault_code", None):
        fault_code = status_obj.fault_code
    elif payload.get("fault_code"):
        fault_code = payload.get("fault_code")
    fault_norm = normalize_fault(fault_code)
    if fault_norm:
        reasons.append(f"Fault: {fault_norm}")

    return [escape_html(str(reason)) for reason in reasons if reason][:3]


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
        if room.room == UNASSIGNED_ROOM_NAME:
            overview.rooms_unassigned += 1
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
        unassigned_hint = (
            "<small style='color:#dc3545;'>Есть устройства без помещения</small>"
            if overview.rooms_unassigned
            else ""
        )
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Помещения (тревоги)</h4>
                    <p>{overview.rooms_with_alarms}/{overview.rooms_total}</p>
                    {unassigned_hint}
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
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Активные аварии</h4>
                    <p>{overview.active_alarms_total}</p>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with col4:
        updated = overview.last_update.strftime("%d.%m %H:%M:%S") if overview.last_update else "—"
        refresh_interval = st.session_state.get("auto_refresh_interval", 60)
        freshness_color = "#238636"
        if not overview.last_update:
            freshness_color = "#ffc107"
        else:
            age = (datetime.utcnow() - overview.last_update).total_seconds()
            if age > max(refresh_interval, 1):
                freshness_color = "#dc3545"
        st.markdown(
            dedent(
                f"""
                <div class="kpi-box">
                    <h4>Последнее обновление</h4>
                    <p style="color:{freshness_color};">{updated}</p>
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

        room_pref[device.device_id] = list(room_pref[device.device_id])

    return {device_id: list(keys) for device_id, keys in room_pref.items()}


def update_room_metric_preferences(room: RoomSnapshot, selection: Dict[int, List[str]]) -> None:
    prefs = st.session_state.setdefault("room_metric_prefs", {})
    prefs[room.room] = selection
    persist_user_preferences()


def get_room_device_metrics(room: RoomSnapshot) -> Dict[int, Dict[str, MetricRecord]]:
    if getattr(room, "device_metrics", None):
        filtered: Dict[int, Dict[str, MetricRecord]] = {}
        for device_id, metrics in room.device_metrics.items():
            filtered[device_id] = dict(metrics)
        return filtered

    # Fallback: собираем из плоского snapshot.metrics
    grouped: Dict[int, Dict[str, MetricRecord]] = {}
    for key, record in room.metrics.items():
        if not record or record.device_id is None:
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
        raw_status = None
        if status and getattr(status, "status", None):
            raw_status = status.status
        elif payload.get("status"):
            raw_status = payload.get("status")
        status_human = humanize_status(raw_status)

        connection_state = None
        if status and getattr(status, "connection_status", None):
            connection_state = status.connection_status
        elif payload.get("connection_status"):
            connection_state = payload.get("connection_status")

        alarms_value = None
        if status and getattr(status, "active_alarms", None) is not None:
            alarms_value = status.active_alarms
        elif payload.get("active_alarms") is not None:
            alarms_value = payload.get("active_alarms")
        alarm_value_int = normalize_int(alarms_value)

        status_ok = (
            (status_human is None or status_human.lower() in STATUS_OK_VALUES)
            and (connection_state is None or is_status_ok(connection_state))
            and alarm_value_int == 0
        )

        problem_reasons = []
        if not status_ok:
            problem_reasons = collect_problem_reasons(
                status_obj=status,
                payload=payload,
                human_status=status_human,
                alarms_count=alarm_value_int,
            )
        detail_html = "<br/>".join(problem_reasons)

        st.markdown(f"#### {device.name} · {device.device_type.value}")

        cards_html: List[str] = []
        alarm_color = "#238636" if status_ok else "#dc3545"
        if status_ok:
            alarm_text = "Норма"
        elif alarm_value_int:
            alarm_text = f"Тревог: {alarm_value_int}"
        elif status_human:
            alarm_text = status_human
        else:
            alarm_text = "Проблема"
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
        raw_status = (
            (status_obj.status if status_obj else None)
            or payload.get("status")
            or (status_obj.connection_status if status_obj else None)
            or payload.get("connection_status")
        )
        status_human = humanize_status(raw_status)

        connection_state = None
        if status_obj and getattr(status_obj, "connection_status", None):
            connection_state = status_obj.connection_status
        elif payload.get("connection_status"):
            connection_state = payload.get("connection_status")

        alarms_value = None
        if status_obj and status_obj.active_alarms is not None:
            alarms_value = status_obj.active_alarms
        elif payload.get("active_alarms") is not None:
            alarms_value = payload.get("active_alarms")
        alarms_count = normalize_int(alarms_value)

        status_ok = (
            (status_human is None or status_human.lower() in STATUS_OK_VALUES)
            and (connection_state is None or is_status_ok(connection_state))
            and alarms_count == 0
        )

        problem_reasons = []
        if not status_ok:
            problem_reasons = collect_problem_reasons(
                status_obj=status_obj,
                payload=payload,
                human_status=status_human,
                alarms_count=alarms_count,
            )
        detail_html = "<br/>".join(problem_reasons)
        pill_color = "#238636" if status_ok else "#dc3545"
        updated = parse_timestamp(payload.get("timestamp"))
        updated_str = updated.strftime("%d.%m %H:%M:%S") if updated else "—"

        extra_status_html = ""
        if status_obj:
            if status_obj.alarms:
                extra_status_html = escape_html(status_obj.alarms[0])
            elif status_obj.warnings:
                extra_status_html = escape_html(status_obj.warnings[0])

        status_label = "OK" if status_ok else "Проблема"
        status_html = (
            f'<div class="device-card">'
            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
            f'<div>'
            f'<strong>{device.name}</strong><br/>'
            f'<small>ID {device.device_id} · Slave {device.slave_id} · {device.device_type.value}</small><br/>'
            f'<small>Обновлено: {updated_str}</small><br/>'
            f'{f"<small>{extra_status_html}</small>" if extra_status_html else ""}'
            f'</div>'
            f'<div class="status-pill" style="background-color:{pill_color}22; color:{pill_color};">'
            f'<div style="display:flex; flex-direction:column; align-items:flex-end;">'
            f'<span>{status_label}</span>'
            f'{f"<small>{detail_html}</small>" if detail_html else ""}'
            f'</div>'
            f'</div>'
            f'</div>'
            f'</div>'
        )

        st.markdown(status_html, unsafe_allow_html=True)

        metric_keys = DEVICE_METRICS.get(device.device_type.value)
        if not metric_keys:
            metric_keys = [key for key in payload.keys() if key in METRIC_DESCRIPTORS]
        if not metric_keys:
            st.write("Нет описанных метрик для отображения")
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
        available_keys |= set(payload.keys())
        available_keys |= set(device_snapshot.keys())
        available_keys -= ALWAYS_ON_METRICS
        available_keys -= DEVICE_STATUS_FIELDS

        if not available_keys:
            continue

        current_selection = preferences.get(device.device_id, [])
        with st.expander(f"{device.name} · {device.device_type.value}", expanded=False):
            device_selection: List[str] = []
            for key in sorted(available_keys):
                checkbox_key = f"pref::{room.room}::{device.device_id}::{key}"
                if checkbox_key not in st.session_state:
                    st.session_state[checkbox_key] = key in current_selection
                checked = st.checkbox(resolve_metric_label(room, device, key), key=checkbox_key)
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


def build_alarm_records(rooms: List[RoomSnapshot]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for room in rooms:
        statuses = getattr(room, "device_statuses", {})
        for device in room.devices:
            status = statuses.get(device.device_id)
            if not status:
                continue
            timestamp = status.timestamp or room.timestamp
            timestamp_str = (
                timestamp.strftime("%d.%m %H:%M:%S") if isinstance(timestamp, datetime) else "—"
            )
            if status.alarms:
                for msg in status.alarms:
                    records.append(
                        {
                            "Тип": "Авария",
                            "Сообщение": msg,
                            "Устройство": device.name,
                            "Помещение": room.room,
                            "Локация": room.location or "—",
                            "Время": timestamp_str,
                        }
                    )
            if status.warnings:
                for msg in status.warnings:
                    records.append(
                        {
                            "Тип": "Предупреждение",
                            "Сообщение": msg,
                            "Устройство": device.name,
                            "Помещение": room.room,
                            "Локация": room.location or "—",
                            "Время": timestamp_str,
                        }
                    )
    return records


def render_alarms_tab(rooms: List[RoomSnapshot]) -> None:
    st.subheader("⚠️ Аварии и предупреждения")
    records = build_alarm_records(rooms)
    if not records:
        st.success("Активных аварий и предупреждений нет")
        return
    df = pd.DataFrame(records)
    st.dataframe(df, hide_index=True)


def load_metric_history(device_id: int, metric_key: str, hours: int) -> List[tuple[datetime, float]]:
    since = datetime.utcnow() - timedelta(hours=hours)
    cutoff = since.strftime("%Y-%m-%d %H:%M:%S")
    result: List[tuple[datetime, float]] = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT timestamp, value
                FROM registers_history
                WHERE device_id = ? AND name = ? AND timestamp >= ?
                ORDER BY timestamp
                """,
                (device_id, metric_key, cutoff),
            )
            for row in cur.fetchall():
                ts = row["timestamp"]
                if isinstance(ts, datetime):
                    ts_dt = ts
                else:
                    try:
                        ts_dt = datetime.fromisoformat(str(ts))
                    except Exception:
                        continue
                try:
                    value = float(row["value"])
                except (TypeError, ValueError):
                    continue
                result.append((ts_dt, value))
    except Exception as exc:
        st.warning(f"Не удалось загрузить историю метрики: {exc}")
    return result


def render_charts_tab(rooms: List[RoomSnapshot]) -> None:
    st.subheader("📈 Графики показаний")
    if not rooms:
        st.info("Нет помещений для отображения")
        return

    room_names = [room.room for room in rooms]
    selected_room_name = st.selectbox("Помещение", room_names)
    room = next((r for r in rooms if r.room == selected_room_name), rooms[0])

    if not room.devices:
        st.info("В помещении нет устройств")
        return

    device_options = {f"{d.name} · {d.device_type.value}": d for d in room.devices}
    device_label = st.selectbox("Устройство", list(device_options.keys()))
    device = device_options[device_label]

    meta_keys = list(getattr(room, "metric_metadata", {}).get(device.device_id, {}).keys())
    if not meta_keys:
        meta_keys = list(room.device_metrics.get(device.device_id, {}).keys())
    if not meta_keys:
        st.info("Для устройства нет метрик")
        return

    selected_metric = st.selectbox("Метрика", meta_keys)
    hours = st.slider("Интервал (часы)", 1, 72, 24)

    history = load_metric_history(device.device_id, selected_metric, hours)
    if not history:
        st.info("Нет данных за выбранный период")
        return

    df = pd.DataFrame(history, columns=["timestamp", "value"]).set_index("timestamp")
    st.line_chart(df, width="stretch")
    meta = getattr(room, "metric_metadata", {}).get(device.device_id, {}).get(selected_metric)
    unit = f" {meta.unit}" if meta and meta.unit else ""
    st.caption(f"Период: последние {hours} ч. Значения{unit}.")


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

    tab_titles = ["Дашборд", "Графики", "Аварии"] + (["Конфигурация"] if is_admin else [])
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        render_dashboard_tab(rooms, device_payloads)

    with tabs[1]:
        render_charts_tab(rooms)

    with tabs[2]:
        render_alarms_tab(rooms)

    if is_admin and len(tabs) > 3:
        with tabs[3]:
            render_configuration_tab(registry)


if __name__ == "__main__":
    main()
