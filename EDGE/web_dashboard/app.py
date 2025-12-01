#!/usr/bin/env python3
"""
file: EDGE/web_dashboard/app.py
description: Операторский Streamlit-дашборд для наблюдения за помещениями и устройствами EDGE.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
from textwrap import dedent
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st
import altair as alt

try:  # optional QR generation
    import qrcode
except Exception:  # pragma: no cover - не критично
    qrcode = None

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
from modbus.command_queue import enqueue_register_write
from core.config_manager import get_config
from core.security_manager import get_security_manager
from core.user_preferences import get_user_preferences_service

try:
    TELEGRAM_BOT_USERNAME = getattr(get_config().telegram, "bot_username", None)
except Exception:
    TELEGRAM_BOT_USERNAME = None

if not TELEGRAM_BOT_USERNAME:
    try:
        secrets = get_security_manager().load_encrypted_config("bot_secrets")
        TELEGRAM_BOT_USERNAME = secrets.get("telegram", {}).get("bot_username")
    except Exception:
        TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME")

try:
    from core.device_registry import DeviceInfo, DeviceRegistry, DeviceType
    from core.device_adapters.catalog import DEVICE_DEFINITIONS, import_adapter_class
    from core.device_adapters.factory import get_device_metric_metadata
    from core.user_registry import ALLOWED_ROLES, UserRegistry

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
    last_successful_update: Optional[datetime] = None
    rooms_unassigned: int = 0


STATE_DIR = Path(__file__).resolve().parent / "state"
PREFERENCES_FILE = STATE_DIR / "user_preferences.json"
logger = logging.getLogger(__name__)

RESET_ACCESS_ROLES = {"operator", "engineer", "admin"}


def _current_user_payload() -> dict[str, Any]:
    payload = st.session_state.get("current_user")
    return payload if isinstance(payload, dict) else {}


def _dashboard_user_can_reset() -> bool:
    user = _current_user_payload()
    role = str(user.get("role", "")).lower()
    return role in RESET_ACCESS_ROLES


def _enqueue_dashboard_reset(device: DeviceInfo, room_name: str) -> tuple[bool, str | None]:
    user = _current_user_payload()
    user_label = user.get("name") or "anonymous"
    user_id = user.get("id")
    user_info = f"dashboard_user_{user_id}_{user_label}"
    try:
        command_id = enqueue_register_write(
            device_id=device.device_id,
            slave_id=device.slave_id,
            register=0x0020,
            value=1,
            user_info=user_info,
            source=f"dashboard:{room_name}",
        )
        logger.info(
            "[DASHBOARD] reset command enqueued (device=%s room=%s id=%s user=%s)",
            device.device_id,
            room_name,
            command_id,
            user_label,
        )
        return True, command_id
    except Exception as exc:
        logger.error("❌ Ошибка постановки команды сброса из дашборда: %s", exc)
        return False, str(exc)


def _normalize_interval(value: Any) -> int:
    try:
        ivalue = int(value)
    except Exception:
        ivalue = 60
    if ivalue <= 0:
        ivalue = 60
    return max(60, min(600, ivalue))


def _maybe_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _build_invite_link(code: str) -> Optional[str]:
    if not TELEGRAM_BOT_USERNAME or not code:
        return None
    handle = TELEGRAM_BOT_USERNAME.lstrip("@").strip()
    if not handle:
        return None
    return f"https://t.me/{handle}?start=invite{code}"


def _generate_qr_image(link: str) -> Optional[bytes]:
    if not qrcode or not link:
        return None
    try:
        img = qrcode.make(link)
    except Exception:
        return None
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _sanitize_preferences_payload(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = data or {}
    rooms_source = data.get("rooms", {}) if isinstance(data, dict) else {}
    rooms_data: Dict[str, Dict[int, List[str]]] = {}
    if isinstance(rooms_source, dict):
        for room_name, devices in rooms_source.items():
            if not isinstance(devices, dict):
                continue
            room_devices: Dict[int, List[str]] = {}
            for device_id_raw, metrics in devices.items():
                try:
                    device_id = int(device_id_raw)
                except Exception:
                    continue
                if isinstance(metrics, list):
                    room_devices[device_id] = [
                        str(metric) for metric in metrics if isinstance(metric, str)
                    ]
            rooms_data[room_name] = room_devices

    auto_raw = data.get("auto_refresh", {}) if isinstance(data, dict) else {}
    auto_block = {
        "enabled": bool(auto_raw.get("enabled", True)),
        "interval": _normalize_interval(auto_raw.get("interval", 60)),
    }

    return {"rooms": rooms_data, "auto_refresh": auto_block}


def _load_legacy_preferences() -> Dict[str, Any]:
    if not PREFERENCES_FILE.exists():
        return _sanitize_preferences_payload({})
    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return _sanitize_preferences_payload({})
    return _sanitize_preferences_payload(data)


def _save_legacy_preferences(payload: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(PREFERENCES_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Логировать не будем, чтобы не мешать UI
        pass


def _resolve_current_user_id() -> Optional[int]:
    current = st.session_state.get("current_user")
    if not current:
        return None
    try:
        return int(current.get("id"))
    except (TypeError, ValueError):
        return None


def _load_preferences_for_user(user_id: Optional[int]) -> tuple[Dict[str, Any], Optional[str]]:
    if user_id is None:
        return INITIAL_USER_PREFS, None
    try:
        service = get_user_preferences_service()
        record = service.load(user_id)
        if record:
            payload = _sanitize_preferences_payload(record.payload)
            return payload, record.updated_at.isoformat()
    except Exception as exc:
        logger.warning("Не удалось загрузить пользовательские настройки: %s", exc)
    return INITIAL_USER_PREFS, None


def _save_preferences_for_user(user_id: Optional[int], payload: Dict[str, Any]) -> None:
    if user_id is None:
        _save_legacy_preferences(payload)
        return
    try:
        service = get_user_preferences_service()
        service.save(user_id, payload)
    except Exception as exc:
        logger.warning("Не удалось сохранить настройки в БД, используем fallback: %s", exc)
        _save_legacy_preferences(payload)


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
    user_id = _resolve_current_user_id()
    _save_preferences_for_user(user_id, snapshot)
    st.session_state["_user_prefs_cache"] = serialized


INITIAL_USER_PREFS = _load_legacy_preferences()


def ensure_preferences_loaded_for_user(current_user: dict[str, Any]) -> None:
    user_id = None
    if current_user:
        try:
            user_id = int(current_user.get("id"))
        except (TypeError, ValueError):
            user_id = None

    marker = st.session_state.get("_prefs_loaded_for_user")
    remote_ts = st.session_state.get("_remote_prefs_ts")
    cached_ts = st.session_state.get("_last_loaded_prefs_ts")
    if (
        marker == user_id
        and st.session_state.get("room_metric_prefs") is not None
        and remote_ts
        and remote_ts == cached_ts
    ):
        st.session_state["auto_refresh_interval"] = _normalize_interval(
            st.session_state.get("auto_refresh_interval", 60)
        )
        _ensure_prefs_cache_initialized()
        return

    payload, remote_ts = _load_preferences_for_user(user_id)
    if remote_ts:
        st.session_state["_remote_prefs_ts"] = remote_ts
    st.session_state["room_metric_prefs"] = payload.get("rooms", {})
    auto_block = payload.get("auto_refresh", {})
    st.session_state["auto_refresh_enabled"] = bool(auto_block.get("enabled", True))
    st.session_state["auto_refresh_interval"] = _normalize_interval(
        auto_block.get("interval", 60)
    )
    st.session_state["_prefs_loaded_for_user"] = user_id
    st.session_state["_last_loaded_prefs_ts"] = st.session_state.get("_remote_prefs_ts")
    _ensure_prefs_cache_initialized()


def _room_anchor(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    slug = slug.strip("-") or "room"
    return f"room-{slug}"


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
        keys = list(metadata.keys())
        if not keys:
            try:
                adapter_cls = import_adapter_class(definition)
                adapter = adapter_cls()
                reg_map = getattr(adapter, "register_map", {})
                if callable(reg_map):
                    reg_map = reg_map()
                if isinstance(reg_map, dict):
                    keys = list(reg_map.keys())
            except Exception:
                keys = []
        mapping[definition.type] = keys
    return mapping


DEVICE_METRICS = build_device_metrics_map()


def build_adapter_default_metrics() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for definition in DEVICE_DEFINITIONS:
        try:
            adapter_cls = import_adapter_class(definition)
        except Exception:
            continue
        defaults = getattr(adapter_cls, "DEFAULT_DASHBOARD_METRICS", None)
        if defaults:
            mapping[definition.type] = list(defaults)
    return mapping


ADAPTER_DEFAULT_METRICS = build_adapter_default_metrics()


def default_metrics_for_device(device_type: str) -> List[str]:
    if device_type in ADAPTER_DEFAULT_METRICS:
        return [
            key
            for key in ADAPTER_DEFAULT_METRICS[device_type]
            if key not in ALWAYS_ON_METRICS
        ][:6]

    keys = DEVICE_METRICS.get(device_type)
    if keys:
        return [key for key in keys if key not in ALWAYS_ON_METRICS][:6]
    try:
        dtype = DeviceType(device_type)
        metadata = get_device_metric_metadata(dtype)
        if metadata:
            return [key for key in metadata.keys() if key not in ALWAYS_ON_METRICS][:6]
    except Exception:
        pass
    return [key for key in DEFAULT_ROOM_METRICS if key not in ALWAYS_ON_METRICS]

STATUS_OK_VALUES = {"ok", "online", "connected", "ready", "active", "normal"}
STALE_DATA_THRESHOLD_SECONDS = 60
STATUS_HUMAN_READABLE = {
    "offline": "Нет связи",
    "disconnected": "Нет связи",
    "error": "Ошибка",
    "fault": "Авария",
    "stop": "Остановлено",
}
ADMIN_PIN_ENV = os.getenv("EDGE_DASHBOARD_ADMIN_PIN")


@st.cache_resource(show_spinner=False)
def get_user_registry() -> UserRegistry:
    return UserRegistry()


def get_admin_pin() -> Optional[str]:
    pin = ADMIN_PIN_ENV
    if pin:
        return pin
    try:
        return st.secrets.get("dashboard_admin_pin")  # type: ignore[attr-defined]
    except Exception:
        return None


def ensure_user_session() -> dict[str, Any]:
    """Гейт авторизации: без пользователя остальной UI не отображается."""

    registry = get_user_registry()
    admin_pin = get_admin_pin()
    if admin_pin:
        registry.ensure_default_admin(admin_pin)

    current = st.session_state.get("current_user")
    if current:
        return current

    users = registry.list_users(active_only=True)
    col_left, col_center, col_right = st.columns([1, 1.2, 1])
    with col_center:
        st.markdown("## 🔐 Вход в EDGE Dashboard")
        if users:
            selected_index = st.selectbox(
                "Пользователь",
                range(len(users)),
                format_func=lambda idx: f"{users[idx].display_name} ({users[idx].role})",
                key="gate_user_select",
            )
            pin_value = st.text_input("PIN", type="password", key="gate_pin_input")
            if st.button("Войти", key="gate_login_btn"):
                selected_user = users[selected_index]
                if registry.authenticate(selected_user.id, pin_value):
                    session_payload = {
                        "id": selected_user.id,
                        "name": selected_user.display_name,
                        "role": selected_user.role,
                        "telegram_id": selected_user.telegram_id,
                    }
                    st.session_state["current_user"] = session_payload
                    st.success("Добро пожаловать!")
                    st.rerun()
                else:
                    st.error("Неверный PIN или пользователь деактивирован")
        else:
            st.info("Нет пользователей в реестре — используйте PIN из переменных окружения")
            pin_value = st.text_input("PIN администратора", type="password", key="gate_env_pin")
            if st.button("Войти", key="gate_env_login"):
                if not admin_pin or pin_value == admin_pin:
                    st.session_state["current_user"] = {
                        "id": "env-admin",
                        "name": "Env Admin",
                        "role": "admin",
                        "telegram_id": None,
                    }
                    st.success("Режим администратора активирован")
                    st.rerun()
                else:
                    st.error("Неверный PIN")

    st.stop()


def render_access_controls(current_user: dict[str, Any]) -> bool:
    """Блок в сайдбаре с информацией о текущем пользователе и кнопкой выхода."""

    if not current_user:
        st.warning("Требуется вход")
        return False

    st.success(f"Пользователь: {current_user['name']} ({current_user['role']})")
    if st.button("Выйти", key="sidebar_logout"):
        st.session_state.pop("current_user", None)
        st.rerun()
    return str(current_user.get("role", "")).lower() == "admin"



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


def _render_relay_pill(state: Optional[bool], *, emergency: bool = False) -> str:
    base_class = "relay-pill relay-pill-unknown"
    text = "Н/Д"
    if state is True:
        base_class = "relay-pill relay-pill-on"
        text = "ВКЛ"
    elif state is False:
        base_class = "relay-pill relay-pill-off"
        text = "ВЫКЛ"
    if emergency:
        base_class += " relay-pill-emergency"
    return f"<span class=\"{base_class}\">{text}</span>"


def _normalize_relay_assignments(data: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if isinstance(data, list):
        source = data
    elif isinstance(data, dict):
        source = data.values()
    else:
        return entries

    for item in source:
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _find_relay_assignment(data: Any, key: str) -> Optional[Dict[str, Any]]:
    for entry in _normalize_relay_assignments(data):
        if entry.get("key") == key:
            return entry
    return None


def format_kub1063_emergency_relay(
    payload: Dict[str, Any], status: Optional[Any], device: DeviceInfo
) -> tuple[Optional[str], Optional[bool]]:
    """Определяет состояние аварийного реле для КУБ-1063."""
    if device.device_type.value != "KUB-1063":
        return None, None

    detected_state: Optional[bool] = None

    def _make_response(state: Optional[bool], label_suffix: str = "") -> Optional[str]:
        nonlocal detected_state
        if state is None:
            return None
        detected_state = state
        pill = _render_relay_pill(state, emergency=True)
        return f"Состояние аварийного реле{label_suffix}: {pill}"

    relay_assignments = payload.get("relay_assignments")
    relay_info = _find_relay_assignment(relay_assignments, "emergency")
    if isinstance(relay_info, dict):
        state = relay_info.get("state")
        channel_label = relay_info.get("channel_label")
        if state is not None:
            label = f" ({channel_label})" if channel_label else ""
            html = _make_response(bool(state), label)
            if html:
                return html, detected_state

        channel = relay_info.get("channel")
        if isinstance(channel, int) and channel >= 0:
            state = None
            if channel < 8:
                state = _read_digital_output("digital_outputs_2", channel)
                if state is None:
                    state = _read_digital_output("digital_outputs_1", channel)
            elif channel < 16:
                state = _read_digital_output("digital_outputs_3", channel - 8)
            else:
                state = _read_digital_output("digital_outputs_3", channel - 16)
            if state is not None:
                label = f" ({channel_label})" if channel_label else ""
                html = _make_response(state, label)
                if html:
                    return html, detected_state

    def _resolve_channel() -> Optional[int]:
        channel = payload.get("emergency_relay_channel")
        if channel is None and status and getattr(status, "emergency_relay_channel", None) is not None:
            channel = status.emergency_relay_channel
        if channel is None:
            return None
        try:
            channel_int = int(channel)
        except (TypeError, ValueError):
            return None
        return channel_int if channel_int >= 0 else None

    def _read_digital_output(group: str, bit: int) -> Optional[bool]:
        value = payload.get(group)
        if value is None:
            return None
        try:
            mask = int(value)
        except (TypeError, ValueError):
            return None
        return bool(mask & (1 << bit))

    channel = _resolve_channel()

    if channel is not None:
        state = None
        if channel < 8:
            state = _read_digital_output("digital_outputs_2", channel)
            if state is None:
                state = _read_digital_output("digital_outputs_1", channel)
        elif channel < 16:
            state = _read_digital_output("digital_outputs_3", channel - 8)
        else:
            state = _read_digital_output("digital_outputs_3", channel - 16)
        if state is not None:
            html = _make_response(state)
            if html:
                return html, detected_state

    # Если канал не определён, пробуем бит аварии в digital_outputs_2
    state = _read_digital_output("digital_outputs_2", 7)
    if state is not None:
        html = _make_response(state)
        if html:
            return html, detected_state

    return "Состояние аварийного реле: —", detected_state


def format_kub1063_relay_cards(payload: Dict[str, Any], device: DeviceInfo) -> Optional[str]:
    if device.device_type.value != "KUB-1063":
        return None

    entries = _normalize_relay_assignments(payload.get("relay_assignments"))
    if not entries:
        return None

    entries.sort(key=lambda item: (str(item.get("category")), item.get("order", 0)))
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        category = str(entry.get("category") or "Реле")
        grouped.setdefault(category, []).append(entry)

    sections: List[str] = []
    for category, group in grouped.items():
        cards: List[str] = []
        for item in group:
            channel_label = item.get("channel_label")
            channel_number = item.get("channel")
            channel_type = item.get("channel_type", "relay")
            if channel_label:
                channel_display = channel_label
            elif isinstance(channel_number, int) and channel_number >= 0:
                if channel_type == "analog_input":
                    channel_display = f"AI{channel_number + 1}"
                elif channel_type == "analog_output":
                    channel_display = f"AO{channel_number + 1}"
                else:
                    channel_display = f"K{channel_number + 1}"
            else:
                channel_display = "Нет назначения"

            register_addr = item.get("register")
            register_display = f"0x{int(register_addr):04X}" if isinstance(register_addr, int) else "—"

            state_value = item.get("state")
            if state_value is True:
                state_variant = "relay-state-on"
                state_text = "ВКЛ"
            elif state_value is False:
                state_variant = "relay-state-off"
                state_text = "ВЫКЛ"
            else:
                if channel_type.startswith("analog") and channel_number is not None:
                    state_variant = "relay-state-assigned"
                    state_text = "Назначено"
                else:
                    state_variant = "relay-state-unknown"
                    state_text = "Н/Д"

            extra_state_classes = []
            if item.get("key") == "emergency":
                extra_state_classes.append("relay-state-emergency")
            state_class = " ".join(["relay-card-state", state_variant, *extra_state_classes]).strip()

            cards.append(
                "".join(
                    [
                        "<div class=\"relay-card\">",
                        f"<small>{escape_html(item.get('label', ''))}</small>",
                        f"<div class=\"relay-card-channel\">{channel_display}</div>",
                        f"<div class=\"relay-card-meta\">Регистр {register_display}</div>",
                        f"<div class=\"{state_class}\">{state_text}</div>",
                        "</div>",
                    ]
                )
            )

        sections.append(
            "".join(
                [
                    "<div class=\"relay-category\">",
                    f"<div class=\"relay-category-title\">{escape_html(category)}</div>",
                    f"<div class=\"relay-grid\">{''.join(cards)}</div>",
                    "</div>",
                ]
            )
        )

    return f"<div class='relay-section'><h5>Назначения реле</h5>{''.join(sections)}</div>"


def _is_preference_metric(device: DeviceInfo, key: str) -> bool:
    if key not in METRIC_DESCRIPTORS:
        return False
    device_type = device.device_type.value
    if device_type == "KUB-1063":
        technical_suffixes = (
            "_relay_channel",
            "_signal_channel",
            "_input_channel",
        )
        if key.endswith(technical_suffixes):
            return False
        if key == "relay_assignments":
            return False
    return True


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
    essential_keys = {
        "connection_status",
        "status",
        "digital_outputs_1",
        "digital_outputs_2",
        "digital_outputs_3",
        "emergency_relay_channel",
        "relay_assignments",
    }
    for device in registry.get_devices(enabled_only=True):
        try:
            payload = registry.get_device_data(device.device_id) or {}
        except Exception as exc:  # pragma: no cover - defensive
            st.warning(f"⚠️ Не удалось получить данные устройства {device.device_id}: {exc}")
            payload = {}

        connection_status = payload.get("connection_status")
        status_value = payload.get("status")
        connection_ok = is_status_ok(connection_status) if connection_status else False
        status_ok = is_status_ok(status_value) if status_value else False

        if not (connection_ok or status_ok):
            reduced = {k: payload.get(k) for k in essential_keys if k in payload}
            for idx in range(4):
                key = f"active_alarms_{idx}"
                if key in payload:
                    reduced[key] = payload[key]
                key = f"registered_alarms_{idx}"
                if key in payload:
                    reduced[key] = payload[key]
            payload = reduced

        payloads[device.device_id] = payload
    return payloads


def render_device_detail_panel(device: DeviceInfo, payload: Dict[str, Any]) -> None:
    st.markdown(
        f"""
**ID**: {device.device_id}  
**Slave**: {device.slave_id}  
**Тип**: {device.device_type.value}  
**Помещение**: {device.room or '—'}  
**Локация**: {device.location or '—'}
"""
    )

    metric_keys = DEVICE_METRICS.get(device.device_type.value) or list(payload.keys())
    if metric_keys:
        cols = st.columns(min(4, len(metric_keys)))
        for idx, key in enumerate(metric_keys):
            column = cols[idx % len(cols)]
            with column:
                label = default_metric_label(device.device_type.value, key)
                value = payload.get(key)
                column.metric(label, format_metric_value(key, value))
    else:
        st.info("Нет описанных показателей для этого устройства")

    st.markdown("---")
    st.subheader("Все данные")
    if payload:
        rows = []
        for k, v in payload.items():
            text = "—" if v is None else str(v)
            rows.append({"Параметр": k, "Значение": text})
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch")
    else:
        st.info("Нет данных — ожидайте опрос")


def render_devices_tab(registry: DeviceRegistry, device_payloads: Dict[int, Dict[str, Any]]) -> None:
    st.subheader("🗂️ Устройства")
    devices = registry.get_devices(enabled_only=True)

    rooms = sorted({d.room or "—" for d in devices})
    types = sorted({d.device_type.value for d in devices})

    c1, c2, c3 = st.columns(3)
    with c1:
        room_filter = st.multiselect("Помещение", rooms, default=rooms)
    with c2:
        type_filter = st.multiselect("Тип устройства", types, default=types)
    with c3:
        search = st.text_input("Поиск по имени/ID/slave", "").strip().lower()

    filtered: List[DeviceInfo] = []
    for device in devices:
        if (device.room or "—") not in room_filter:
            continue
        if device.device_type.value not in type_filter:
            continue
        if search:
            haystack = f"{device.device_id} {device.slave_id} {device.name} {device.location or ''}".lower()
            if search not in haystack:
                continue
        filtered.append(device)

    rows = []
    for dev in filtered:
        payload = device_payloads.get(dev.device_id) or {}
        status = payload.get("connection_status") or payload.get("status") or "unknown"
        rows.append(
            {
                "ID": dev.device_id,
                "Slave": dev.slave_id,
                "Имя": dev.name,
                "Тип": dev.device_type.value,
                "Помещение": dev.room or "—",
                "Локация": dev.location or "—",
                "Статус": status,
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch")

    st.markdown("---")
    st.subheader("🔍 Детали устройства")
    options = [dev.device_id for dev in filtered] or [d.device_id for d in devices]
    selected_id = st.selectbox(
        "Выберите устройство",
        options,
        format_func=lambda did: next((d.name for d in devices if d.device_id == did), str(did)),
    )

    selected_device = registry.get_device(selected_id)
    if not selected_device:
        st.info("Устройство не найдено")
        return

    payload = device_payloads.get(selected_id) or {}
    render_device_detail_panel(selected_device, payload)


def build_overview(rooms: List[RoomSnapshot], device_payloads: Dict[int, Dict[str, Any]]) -> FarmOverview:
    overview = FarmOverview()
    overview.rooms_total = len(rooms)
    overview.rooms_with_alarms = sum(1 for room in rooms if room.alarms.get("active_alarms", 0))
    overview.devices_total = len(device_payloads)

    alarm_total = 0
    timestamps: List[datetime] = []
    success_timestamps: List[datetime] = []
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
        elif ts:
            success_timestamps.append(ts)

    overview.active_alarms_total = alarm_total
    overview.avg_temp = sum(temps) / len(temps) if temps else None
    overview.last_update = max(timestamps) if timestamps else None
    overview.last_successful_update = (
        max(success_timestamps) if success_timestamps else overview.last_update
    )
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
        updated_dt = overview.last_successful_update
        updated = updated_dt.strftime("%d.%m %H:%M:%S") if updated_dt else "—"
        freshness_color = "#238636"
        if not updated_dt:
            freshness_color = "#dc3545"
        else:
            age = (datetime.utcnow() - updated_dt).total_seconds()
            if age > STALE_DATA_THRESHOLD_SECONDS:
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
        default_keys = set(default_metrics_for_device(device.device_type.value))
        default_keys -= ALWAYS_ON_METRICS
        default_keys -= DEVICE_STATUS_FIELDS

        if device.device_id not in room_pref:
            room_pref[device.device_id] = list(default_keys)

        current_selection = [key for key in room_pref[device.device_id] if key in ALLOWED_METRIC_KEYS]
        if not current_selection:
            # если пользователь ничего не выбирал или все ключи устарели — возвращаемся к дефолту
            current_selection = list(default_keys)
        room_pref[device.device_id] = current_selection

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
        if not payload:
            device_snapshot = {}
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

        problem_reasons: List[str] = []
        if not status_ok:
            problem_reasons = collect_problem_reasons(
                status_obj=status,
                payload=payload,
                human_status=status_human,
                alarms_count=alarm_value_int,
            )

        detail_segments: List[str] = []
        if problem_reasons:
            detail_segments.append("<br/>".join(problem_reasons))

        relay_detail, detected_emergency_state = format_kub1063_emergency_relay(
            payload, status, device
        )
        if relay_detail:
            detail_segments.append(relay_detail)

        detail_html = "<br/>".join(detail_segments)

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
        state_class = "ok" if status_ok else "error"
        cards_html.append(
            dedent(
                f"""
                <div class="metric-card status-{state_class}">
                    <div class="metric-card-marker" style="background-color:{alarm_color};"></div>
                    <div class="metric-card-content">
                        <small>Аварии</small>
                        <h4 style="margin: 6px 0; color:{alarm_color};">{alarm_text}</h4>
                        <small>{detail_html}</small>
                    </div>
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

        relay_flag = bool(payload.get("alarm_relay")) if "alarm_relay" in payload else False
        if detected_emergency_state is True:
            relay_flag = True
        show_reset = ((alarm_value_int or 0) > 0) or relay_flag
        if show_reset and _dashboard_user_can_reset() and device.device_type.value == "KUB-1063":
            room_name = room.room or "room"
            room_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", room_name)
            reset_cols = st.columns([0.35, 0.65])
            btn_label = "🔁 Сброс аварии"
            if reset_cols[0].button(
                btn_label,
                key=f"reset_alarm_{room_slug}_{device.device_id}",
                help="Отправляет команду записи регистра 0x0020 на устройстве",
            ):
                success, command_id = _enqueue_dashboard_reset(device, room_name)
                if success and command_id:
                    reset_cols[1].success(f"Команда отправлена (ID {command_id})")
                else:
                    reset_cols[1].error(f"Не удалось отправить команду: {command_id or 'ошибка'}")

        relay_cards_html = format_kub1063_relay_cards(payload, device)
        if relay_cards_html:
            with st.expander("Назначения реле", expanded=False):
                st.markdown(relay_cards_html, unsafe_allow_html=True)


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
        base_keys = set(DEVICE_METRICS.get(device.device_type.value, []))
        fallback_keys = set(payload.keys()) | set(device_snapshot.keys())
        candidate_keys = base_keys | fallback_keys

        available_keys = {
            key
            for key in candidate_keys
            if key not in ALWAYS_ON_METRICS
            and key not in DEVICE_STATUS_FIELDS
            and _is_preference_metric(device, key)
        }

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
    anchor = _room_anchor(room.room)
    st.markdown(f"<div class='room-frame' id='{anchor}'>", unsafe_allow_html=True)
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

    st.markdown("</div>", unsafe_allow_html=True)


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

    meta_bucket = getattr(room, "metric_metadata", {}).get(device.device_id, {})
    metric_keys: List[str] = []
    seen: set[str] = set()

    for key in meta_bucket.keys():
        if key not in seen:
            seen.add(key)
            metric_keys.append(key)
    for key in room.device_metrics.get(device.device_id, {}).keys():
        if key not in seen:
            seen.add(key)
            metric_keys.append(key)
    if not metric_keys:
        st.info("Для устройства нет метрик")
        return

    selected_metric = st.selectbox(
        "Метрика",
        metric_keys,
        format_func=lambda key: resolve_metric_label(room, device, key),
    )
    hours = st.slider("Интервал (часы)", 1, 72, 24)

    history = load_metric_history(device.device_id, selected_metric, hours)
    if not history:
        st.info("Нет данных за выбранный период")
        return

    df = pd.DataFrame(history, columns=["timestamp", "value"])
    chart = (
        alt.Chart(df)
        .mark_line(point=False)
        .encode(
            x=alt.X("timestamp:T", axis=alt.Axis(format="%H:%M", title="Время")),
            y=alt.Y("value:Q", title="Значение"),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Время"),
                alt.Tooltip("value:Q", title="Значение"),
            ],
        )
        .properties(width=800, height=320)
        .interactive()
    )
    st.altair_chart(chart, width="stretch")
    meta = getattr(room, "metric_metadata", {}).get(device.device_id, {}).get(selected_metric)
    unit = f" {meta.unit}" if meta and meta.unit else ""
    st.caption(f"Период: последние {hours} ч. Значения{unit}.")


def render_dashboard_tab(
    rooms: List[RoomSnapshot],
    device_payloads: Dict[int, Dict[str, Any]],
    selected_room: Optional[str] = None,
) -> None:
    if not rooms:
        st.info("Нет активных помещений. Заполните config/devices.yaml")
        return

    overview = build_overview(rooms, device_payloads)
    render_overview(overview)

    st.subheader("🏢 Помещения")
    for room in rooms:
        if selected_room and selected_room != room.room:
            continue
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

def render_user_management_panel() -> None:
    registry = get_user_registry()
    users = registry.list_users(active_only=False)
    if users:
        df = pd.DataFrame(
            [
                {
                    "ID": user.id,
                    "Имя": user.display_name,
                    "Роль": user.role,
                    "Активен": "Да" if user.is_active else "Нет",
                    "Telegram ID": str(user.telegram_id) if user.telegram_id else "—",
                }
                for user in users
            ]
        )
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.info("Пользователей пока нет — создайте первого")

    with st.expander("➕ Добавить пользователя", expanded=False):
        with st.form("create_user_form"):
            name = st.text_input("Имя")
            role = st.selectbox("Роль", ALLOWED_ROLES, format_func=lambda r: r.capitalize())
            pin = st.text_input("PIN", type="password")
            telegram_raw = st.text_input("Telegram ID (опционально)")
            submitted = st.form_submit_button("Создать")
            if submitted:
                if not name or not pin:
                    st.error("Имя и PIN обязательны")
                else:
                    try:
                        telegram_id = _maybe_int(telegram_raw)
                        registry.create_user(name, pin, role=role, telegram_id=telegram_id)
                        st.success("Пользователь создан")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Не удалось создать: {exc}")

    if users:
        with st.expander("✏️ Изменить пользователя", expanded=False):
            options = {f"{u.display_name} (#{u.id})": u for u in users}
            selected_label = st.selectbox("Пользователь", list(options.keys()), key="edit_user_select")
            user = options[selected_label]
            with st.form("edit_user_form"):
                new_name = st.text_input("Имя", value=user.display_name)
                new_role = st.selectbox(
                    "Роль",
                    ALLOWED_ROLES,
                    index=max(0, ALLOWED_ROLES.index(user.role) if user.role in ALLOWED_ROLES else 0),
                )
                new_pin = st.text_input("Новый PIN (опционально)", type="password")
                telegram_raw = st.text_input("Telegram ID", value=str(user.telegram_id or ""))
                active_flag = st.checkbox("Активен", value=user.is_active)
                submitted = st.form_submit_button("Сохранить изменения")
                if submitted:
                    try:
                        registry.update_user(
                            user.id,
                            display_name=new_name,
                            role=new_role,
                            telegram_id=_maybe_int(telegram_raw),
                            is_active=active_flag,
                        )
                        if new_pin:
                            registry.set_pin(user.id, new_pin)
                        st.success("Изменения сохранены")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Не удалось обновить: {exc}")

    with st.expander("✉️ Приглашения для Telegram", expanded=False):
        current_user = st.session_state.get("current_user", {})
        invited_by = current_user.get("telegram_id") if isinstance(current_user.get("telegram_id"), int) else None
        with st.form("create_invite_form"):
            invite_role = st.selectbox("Роль приглашения", ALLOWED_ROLES, index=0)
            valid_hours = st.slider("Срок действия, часов", min_value=1, max_value=168, value=24)
            submitted = st.form_submit_button("Создать приглашение")
            if submitted:
                try:
                    code = registry.create_invitation(
                        invited_by=invited_by, role=invite_role, hours_valid=valid_hours
                    )
                    st.success(f"Приглашение создано: {code}")
                    link = _build_invite_link(code)
                    if link:
                        st.markdown(f"Ссылка: [{link}]({link})")
                        qr_bytes = _generate_qr_image(link)
                        if qr_bytes:
                            st.image(qr_bytes, caption="QR-код приглашения", width=200)
                    st.info("Отправьте код или ссылку пользователю, чтобы он активировал доступ в Telegram-боте.")
                except Exception as exc:
                    st.error(f"Не удалось создать приглашение: {exc}")

        invites = registry.list_invitations()
        if invites:
            table_data = []
            for item in invites:
                link = _build_invite_link(item["code"])
                table_data.append(
                    {
                        "Код": item["code"],
                        "Роль": item["access_level"],
                        "Ссылка": link or "—",
                        "Создан": item["created_at"],
                        "Истекает": item["expires_at"] or "—",
                    }
                )
            st.table(table_data)

            if qrcode:
                selected_code = st.selectbox(
                    "Показать QR для приглашения",
                    [item["code"] for item in invites],
                    format_func=lambda c: f"{c} ({_build_invite_link(c) or 'без ссылки'})",
                    key="invite_qr_select",
                )
                link = _build_invite_link(selected_code)
                if link:
                    qr_bytes = _generate_qr_image(link)
                    if qr_bytes:
                        st.image(qr_bytes, caption=link, width=220)
                    else:
                        st.warning("Не удалось создать QR-код")
        else:
            st.info("Активных приглашений нет")


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

    current_user = ensure_user_session()
    ensure_preferences_loaded_for_user(current_user)
    try:
        rooms, device_payloads = load_data(registry)
    except Exception as exc:
        st.error(f"Не удалось загрузить данные: {exc}")
        return

    room_names: List[str] = [room.room for room in rooms]
    selected_room = st.session_state.get("room_navigation")
    if selected_room == "Все помещения":
        selected_room = None

    with st.sidebar:
        st.header("🔐 Доступ")
        is_admin = render_access_controls(current_user)
        st.header("⚙️ Обновление")
        if st.button("🔄 Обновить настройки", key="reload_user_prefs"):
            st.session_state.pop("_prefs_loaded_for_user", None)
            st.session_state.pop("_remote_prefs_ts", None)
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        auto_refresh_enabled = st.checkbox("Автообновление", key="auto_refresh_enabled")
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

        st.divider()
        st.header("🏠 Навигация")
        if room_names:
            nav_options = ["Все помещения"] + room_names
            choice = st.radio("Отобразить", nav_options, index=0, key="room_navigation")
            if choice != "Все помещения":
                selected_room = choice
            st.caption("Быстрые ссылки")
            for room in room_names:
                anchor = _room_anchor(room)
                st.markdown(f"- <a href='#{anchor}'>{room}</a>", unsafe_allow_html=True)
        else:
            st.caption("Нет помещений")

        st.divider()
        st.header("ℹ️ Справка")
        st.caption("Документация и подробные инструкции будут добавлены позже.")

    if refresh_now:
        st.rerun()

    if st.session_state.get("auto_refresh_enabled") and st_autorefresh is not None:
        st_autorefresh(
            interval=_normalize_interval(st.session_state.get("auto_refresh_interval", 60)) * 1000,
            key="edge_dashboard_autorefresh",
        )

    tab_titles = ["Дашборд", "Устройства", "Графики", "Аварии"] + (["Конфигурация", "Пользователи"] if is_admin else [])
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        render_dashboard_tab(rooms, device_payloads, selected_room)

    with tabs[1]:
        render_devices_tab(registry, device_payloads)

    with tabs[2]:
        render_charts_tab(rooms)

    with tabs[3]:
        render_alarms_tab(rooms)

    if is_admin and len(tabs) > 4:
        with tabs[4]:
            render_configuration_tab(registry)
        with tabs[5]:
            render_user_management_panel()


if __name__ == "__main__":
    main()
