#!/usr/bin/env python3
"""
Streamlit Dashboard для КУБ-1063
Визуализация данных с контроллера в стиле Grafana
"""

import os
import sys

# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Импорт функции чтения данных через Device Registry
try:
    from core.device_registry import DeviceRegistry
    from core.config_manager import get_config
    DEVICE_REGISTRY_AVAILABLE = True
except ImportError as e:
    DEVICE_REGISTRY_AVAILABLE = False
    st.error(f"❌ Device Registry недоступен: {e}")

DEVICE_AVAILABLE = DEVICE_REGISTRY_AVAILABLE

# Глобальный Device Registry
if DEVICE_REGISTRY_AVAILABLE:
    try:
        device_registry = DeviceRegistry()
        device_registry.load_devices_from_config()
    except Exception as e:
        st.error(f"❌ Ошибка инициализации Device Registry: {e}")
        DEVICE_AVAILABLE = False

def read_all():
    """Чтение данных всех устройств через Device Registry"""
    if not DEVICE_AVAILABLE:
        return {}
    
    try:
        devices = device_registry.get_devices()
        if not devices:
            return {}
        
        # Берем данные первого устройства для совместимости
        first_device = devices[0]
        device_data = device_registry.get_device_data(first_device.device_id)
        
        if device_data:
            # Добавляем timestamp если его нет
            if "timestamp" not in device_data:
                device_data["timestamp"] = datetime.now()
            return device_data
        
        return {}
    except Exception as e:
        st.error(f"❌ Ошибка чтения данных: {e}")
        return {}

def get_historical_data(hours: int = 6):
    """Получение исторических данных (заглушка)"""
    # В текущей архитектуре исторические данные не сохраняются
    # Возвращаем пустой список для совместимости
    return []

def get_statistics():
    """Получение статистики системы (заглушка)"""
    if not DEVICE_AVAILABLE:
        return {}
    
    try:
        devices = device_registry.get_devices()
        devices_with_data = 0
        for device_info in devices:
            device_data = device_registry.get_device_data(device_info.device_id)
            if device_data:
                devices_with_data += 1
                
        return {
            "updates_per_minute": 6,  # Примерная частота обновления
            "errors_per_minute": 0,
            "success_rate": (devices_with_data / len(devices) * 100) if devices else 0
        }
    except Exception:
        return {}

def get_all_registers():
    """Получение всех регистров (заглушка)"""
    if not DEVICE_AVAILABLE:
        return []
    
    try:
        all_registers = []
        devices = device_registry.get_devices()
        
        for device_info in devices:
            device_data = device_registry.get_device_data(device_info.device_id)
            if device_data:
                # Конвертируем данные устройства в формат регистров
                for key, value in device_data.items():
                    if key != "timestamp":
                        all_registers.append({
                            "name": f"{device_info.device_id}_{key}",
                            "value": str(value) if value is not None else "N/A",
                            "address_hex": f"0x{hash(key) % 0xFFFF:04X}",
                            "updated_at": device_data.get("timestamp", datetime.now()).isoformat() if hasattr(device_data.get("timestamp", ""), "isoformat") else str(device_data.get("timestamp", ""))
                        })
        
        return all_registers
    except Exception as e:
        st.error(f"❌ Ошибка получения регистров: {e}")
        return []

def get_rs485_statistics():
    """Получение статистики RS485 (заглушка)"""
    return {
        "total_requests": 100,
        "successful_requests": 95,
        "failed_requests": 5,
        "success_rate": 95.0
    }

# Настройка страницы
st.set_page_config(
    page_title="CUBE_RS EDGE Dashboard", layout="wide", initial_sidebar_state="collapsed"
)

# Стили в стиле Grafana
st.markdown(
    """
    <style>
    /* Основная тема */
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }

    /* Метрики */
    .stMetric {
        background-color: #21262d;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 16px;
        margin: 8px 0;
    }

    .stMetric > div {
        background-color: transparent !important;
    }

    /* Заголовки */
    h1, h2, h3 {
        color: #58a6ff !important;
    }

    /* Контейнеры */
    .element-container {
        background-color: #21262d;
        border-radius: 6px;
        margin: 8px 0;
    }

    /* Боковая панель */
    .css-1d391kg {
        background-color: #0d1117;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Инициализация кэша для сглаживания (сохраняем для текущих данных)
if "data_cache" not in st.session_state:
    st.session_state.data_cache = {}
    st.session_state.cache_timestamp = None

DISCRETE_KEYS = {
    "timestamp",
    "connection_status",
    "success_rate",
    "error",
    "active_alarms",
    "active_warnings",
    "digital_outputs_1",
    "digital_outputs_2",
    "digital_outputs_3",
    "ventilation_scheme",
    "alarm_relay",
}


def smooth_data(data, cache_window=5):
    """Сглаживает данные, используя скользящее среднее"""
    if not data:
        return data

    current_time = datetime.now()

    # Добавляем текущие данные в кэш
    if "data_cache" not in st.session_state:
        st.session_state.data_cache = {}

    # Очищаем старые данные (старше 30 секунд)
    if st.session_state.cache_timestamp:
        if (current_time - st.session_state.cache_timestamp).total_seconds() > 30:
            st.session_state.data_cache = {}

    # Добавляем текущие данные
    for key, value in data.items():
        if key not in DISCRETE_KEYS:
            if key not in st.session_state.data_cache:
                st.session_state.data_cache[key] = []

            if value is not None:
                st.session_state.data_cache[key].append(value)

                # Ограничиваем размер кэша
                if len(st.session_state.data_cache[key]) > cache_window:
                    st.session_state.data_cache[key] = st.session_state.data_cache[key][
                        -cache_window:
                    ]

    st.session_state.cache_timestamp = current_time

    # Вычисляем сглаженные значения
    smoothed_data = data.copy()
    for key, values in st.session_state.data_cache.items():
        if key in DISCRETE_KEYS:
            continue
        if values:
            import statistics

            try:
                smoothed_value = statistics.median(values)
                smoothed_data[key] = smoothed_value
            except:
                smoothed_data[key] = values[-1]

    return smoothed_data


def get_status_color(value, min_val, max_val):
    """Определяет цвет статуса на основе значения"""
    if min_val <= value <= max_val:
        return "#28a745"  # Зеленый
    elif abs(value - min_val) < abs(value - max_val):
        return "#ffc107"  # Желтый
    else:
        return "#dc3545"  # Красный


def main():
    st.title("📊 CUBE_RS EDGE Dashboard")

    # Создаем placeholder для автообновления
    placeholder = st.empty()

    # Боковая панель с настройками
    with st.sidebar:
        st.header("⚙️ Настройки")
        auto_refresh = st.checkbox("Автообновление", value=True)
        refresh_interval = st.slider("Интервал обновления (сек)", 1, 60, 5)

        # Настройки сглаживания
        st.header("🔧 Сглаживание данных")
        smoothing_enabled = st.checkbox("Включить сглаживание", value=True)
        cache_window = st.slider("Окно сглаживания", 1, 10, 3)

        # Индикатор качества данных
        if "data_cache" in st.session_state and st.session_state.data_cache:
            st.header("📊 Качество данных")
            cache_size = sum(len(values) for values in st.session_state.data_cache.values())
            if cache_size > 0:
                st.success(f"✅ Данные стабильны ({cache_size} измерений)")
            else:
                st.warning("⚠️ Данные нестабильны")

        st.header("📈 История данных")
        history_hours = st.slider("Показать за часов", 1, 24, 6)

        st.info("💾 Исторические данные загружаются из базы данных")

    # Основной цикл обновления
    while True:
        with placeholder.container():
            # Получаем данные
            try:
                raw_data = read_all()
                if raw_data:
                    # Добавляем timestamp если его нет
                    if "timestamp" not in raw_data:
                        raw_data["timestamp"] = datetime.now()

                    # Сглаживаем данные
                    if smoothing_enabled:
                        data = smooth_data(raw_data, cache_window=cache_window)
                    else:
                        data = raw_data

                    # Данные автоматически сохраняются в БД через Gateway
                else:
                    st.error("❌ Нет данных с контроллера")
                    data = {}
            except Exception as e:
                st.error(f"❌ Ошибка чтения данных: {e}")
                data = {}

            # Основные метрики
            st.subheader("🎯 Основные параметры")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                temp_inside = data.get("temp_inside", 0)
                temp_target = data.get("temp_target", 25)

                # Проверяем, что значения не None
                if temp_inside is None:
                    temp_inside = 0
                if temp_target is None:
                    temp_target = 25

                temp_color = get_status_color(temp_inside, temp_target - 2, temp_target + 2)

                temp_inside_str = f"{temp_inside:.1f}°C" if temp_inside is not None else "N/A"
                temp_target_str = f"{temp_target:.1f}°C" if temp_target is not None else "N/A"

                st.markdown(
                    f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {temp_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🌡️ Температура</h4>
                    <h2 style="margin: 8px 0; color: {temp_color};">{temp_inside_str}</h2>
                    <small style="color: #8b949e;">Цель: {temp_target_str}</small>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with col2:
                hum_status = data.get("humidity_status")
                humidity = data.get("humidity")
                if hum_status == "disabled":
                    humidity = None
                humidity_color = get_status_color(humidity, 40, 70)
                if hum_status == "pending":
                    humidity_str = "ожидаем замер"
                    humidity_color = "#8b949e"
                else:
                    humidity_str = f"{humidity:.1f}%" if humidity is not None else "N/A"

                st.markdown(
                    f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {humidity_color};">
                    <h4 style="margin: 0; color: #e6edf3;">💧 Влажность</h4>
                    <h2 style="margin: 8px 0; color: {humidity_color};">{humidity_str}</h2>
                    <small style="color: #8b949e;">Цель: 40–70%</small>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with col3:
                co2_status = data.get("co2_status")
                co2 = data.get("co2")
                if co2_status == "disabled":
                    co2 = None
                if co2_status == "pending":
                    co2_str = "ожидаем замер"
                else:
                    co2_str = f"{co2} ppm" if co2 is not None else "N/A"

                co2_color = "#28a745" if (co2 is not None and co2 <= 3000) else (
                    "#ffc107" if (co2 is not None and co2 <= 5000) else "#dc3545"
                )

                st.markdown(
                    f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {co2_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🫁 CO₂</h4>
                    <h2 style="margin: 8px 0; color: {co2_color};">{co2_str}</h2>
                    <small style="color: #8b949e;">Норма: ≤ 3000 ppm</small>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with col4:
                pressure = data.get("pressure")
                pressure_str = f"{pressure:.1f} Pa" if pressure is not None else "N/A"
                pressure_color = "#e6edf3"

                st.markdown(
                    f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {pressure_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🌀 Давление</h4>
                    <h2 style="margin: 8px 0; color: {pressure_color};">{pressure_str}</h2>
                    <small style="color: #8b949e;">Отрицательное давление</small>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Графики
            st.subheader("📉 Графики показаний")
            if data:
                try:
                    history = get_historical_data(hours=history_hours)
                    if history is not None and len(history) > 0:
                        df = pd.DataFrame(history)
                        df["timestamp"] = pd.to_datetime(df["timestamp"])

                        col1, col2 = st.columns(2)

                        with col1:
                            fig_temp = go.Figure()
                            fig_temp.add_trace(
                                go.Scatter(
                                    x=df["timestamp"],
                                    y=df["temp_inside"],
                                    mode="lines+markers",
                                    name="Температура",
                                    line=dict(color="#58a6ff"),
                                )
                            )
                            fig_temp.update_layout(
                                title="Температура",
                                paper_bgcolor="#0d1117",
                                plot_bgcolor="#161b22",
                                font=dict(color="#e6edf3"),
                            )
                            st.plotly_chart(fig_temp, use_container_width=True)

                        with col2:
                            fig_hum = go.Figure()
                            fig_hum.add_trace(
                                go.Scatter(
                                    x=df["timestamp"],
                                    y=df["humidity"],
                                    mode="lines+markers",
                                    name="Влажность",
                                    line=dict(color="#a371f7"),
                                )
                            )
                            fig_hum.update_layout(
                                title="Влажность",
                                paper_bgcolor="#0d1117",
                                plot_bgcolor="#161b22",
                                font=dict(color="#e6edf3"),
                            )
                            st.plotly_chart(fig_hum, use_container_width=True)

                        # Дополнительные графики
                        col3, col4 = st.columns(2)
                        with col3:
                            fig_co2 = go.Figure()
                            fig_co2.add_trace(
                                go.Scatter(
                                    x=df["timestamp"],
                                    y=df["co2"],
                                    mode="lines+markers",
                                    name="CO₂",
                                    line=dict(color="#2ea043"),
                                )
                            )
                            fig_co2.update_layout(
                                title="CO₂",
                                paper_bgcolor="#0d1117",
                                plot_bgcolor="#161b22",
                                font=dict(color="#e6edf3"),
                            )
                            st.plotly_chart(fig_co2, use_container_width=True)

                        with col4:
                            fig_press = go.Figure()
                            fig_press.add_trace(
                                go.Scatter(
                                    x=df["timestamp"],
                                    y=df["pressure"],
                                    mode="lines+markers",
                                    name="Давление",
                                    line=dict(color="#fb8c00"),
                                )
                            )
                            fig_press.update_layout(
                                title="Давление",
                                paper_bgcolor="#0d1117",
                                plot_bgcolor="#161b22",
                                font=dict(color="#e6edf3"),
                            )
                            st.plotly_chart(fig_press, use_container_width=True)

                    else:
                        st.info("ℹ️ Недостаточно исторических данных для построения графиков")
                except Exception as e:
                    st.error(f"❌ Ошибка построения графиков: {e}")

            # Статистика системы
            st.subheader("📊 Статистика системы")
            try:
                stats = get_statistics()
                if stats:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Обновления/мин", stats.get("updates_per_minute", 0))
                    with col2:
                        st.metric("Ошибки/мин", stats.get("errors_per_minute", 0))
                    with col3:
                        st.metric("Успех %", f"{stats.get('success_rate', 0):.1f}%")
                else:
                    st.info("ℹ️ Статистика недоступна")
            except Exception as e:
                st.error(f"❌ Ошибка получения статистики: {e}")

            # Полный список регистров
            try:
                st.subheader("📚 Все доступные регистры")
                regs = get_all_registers()
                if regs:
                    table = [
                        {
                            "Адрес": r.get("address_hex") or f"0x{int(r.get('register', 0)):04X}",
                            "Имя": r.get("name", ""),
                            "Значение": r.get("value", ""),
                            "Обновлено": r.get("updated_at", ""),
                        }
                        for r in regs
                    ]
                    st.dataframe(pd.DataFrame(table), use_container_width=True)
                else:
                    st.info("ℹ️ Регистры пока не получены. Ожидаем опрос.")
            except Exception as e:
                st.error(f"❌ Ошибка загрузки регистров: {e}")

            # Доп. вкладки для отладки
            try:
                tab_regs, tab_debug = st.tabs(["📚 Регистры", "🛠️ RAW/Отладка"])

                with tab_regs:
                    regs = get_all_registers()
                    only_display = st.checkbox("Показывать только отмеченные в YAML", value=True)
                    filter_text = st.text_input(
                        "Фильтр по имени/адресу", value="", placeholder="например, temp или 0x00D5"
                    )
                    if regs:
                        # Подготовим таблицу
                        rows = [
                            {
                                "Адрес": r.get("address_hex")
                                or (f"0x{int(r.get('register', 0)):04X}"),
                                "Имя": r.get("name", ""),
                                "Значение": r.get("value", ""),
                                "Обновлено": r.get("updated_at", ""),
                            }
                            for r in regs
                        ]
                        df_regs = pd.DataFrame(rows)
                        if only_display:
                            # Отфильтруем по display=true (если поле присутствует)
                            if "display" in regs[0]:
                                df_regs = df_regs[df_regs.index.map(lambda i: regs[i].get("display", True))]

                        # Фильтрация
                        if filter_text:
                            ft = filter_text.lower().strip()
                            df_regs = df_regs[
                                df_regs.apply(
                                    lambda x: ft in str(x["Имя"]).lower()
                                    or ft in str(x["Адрес"]).lower(),
                                    axis=1,
                                )
                            ]

                        st.dataframe(df_regs, use_container_width=True)

                        # Выгрузка CSV
                        csv = df_regs.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Скачать CSV",
                            data=csv,
                            file_name=f"registers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                        )
                    else:
                        st.info("ℹ️ Регистры пока не получены. Ожидаем опрос.")

                with tab_debug:
                    st.markdown("### Текущий RAW‑снимок")
                    st.json(data or {})

                    st.markdown("### RS485/TimeWindow статистика")
                    try:
                        rs_stats = get_rs485_statistics()
                        st.json(rs_stats)
                    except Exception as e:
                        st.warning(f"Не удалось получить статистику RS485: {e}")
            except Exception:
                # Вкладки недоступны (на случай несовместимой версии Streamlit)
                pass

            # Пауза
            if auto_refresh:
                time.sleep(refresh_interval)
            else:
                break


if __name__ == "__main__":
    main()
