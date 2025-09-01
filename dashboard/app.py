"""
Streamlit Dashboard для КУБ-1063
Визуализация данных с контроллера в стиле Grafana
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import time
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pandas as pd

# Импорт функции чтения данных
from modbus.dashboard_reader import read_all, get_statistics, get_historical_data
DEVICE_AVAILABLE = True

# Настройка страницы
st.set_page_config(
    page_title="КУБ-1063 Dashboard", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Стили в стиле Grafana
st.markdown("""
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
""", unsafe_allow_html=True)

# Инициализация кэша для сглаживания (сохраняем для текущих данных)
if 'data_cache' not in st.session_state:
    st.session_state.data_cache = {}
    st.session_state.cache_timestamp = None

def smooth_data(data, cache_window=5):
    """Сглаживает данные, используя скользящее среднее"""
    if not data:
        return data
    
    current_time = datetime.now()
    
    # Добавляем текущие данные в кэш
    if 'data_cache' not in st.session_state:
        st.session_state.data_cache = {}
    
    # Очищаем старые данные (старше 30 секунд)
    if st.session_state.cache_timestamp:
        if (current_time - st.session_state.cache_timestamp).total_seconds() > 30:
            st.session_state.data_cache = {}
    
    # Добавляем текущие данные
    for key, value in data.items():
        if key not in ['timestamp', 'connection_status', 'success_rate', 'error']:
            if key not in st.session_state.data_cache:
                st.session_state.data_cache[key] = []
            
            if value is not None:
                st.session_state.data_cache[key].append(value)
                
                # Ограничиваем размер кэша
                if len(st.session_state.data_cache[key]) > cache_window:
                    st.session_state.data_cache[key] = st.session_state.data_cache[key][-cache_window:]
    
    st.session_state.cache_timestamp = current_time
    
    # Вычисляем сглаженные значения
    smoothed_data = data.copy()
    for key, values in st.session_state.data_cache.items():
        if values and len(values) > 0:
            # Используем медиану для устойчивости к выбросам
            import statistics
            try:
                smoothed_value = statistics.median(values)
                smoothed_data[key] = smoothed_value
            except:
                smoothed_data[key] = values[-1]  # Последнее значение если медиана не работает
    
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
    st.title("📊 Панель мониторинга КУБ-1063")
    
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
        if 'data_cache' in st.session_state and st.session_state.data_cache:
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
                    if 'timestamp' not in raw_data:
                        raw_data['timestamp'] = datetime.now()
                    
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
                temp_inside = data.get('temp_inside', 0)
                temp_target = data.get('temp_target', 25)
                
                # Проверяем, что значения не None
                if temp_inside is None:
                    temp_inside = 0
                if temp_target is None:
                    temp_target = 25
                    
                temp_color = get_status_color(temp_inside, temp_target - 2, temp_target + 2)
                
                temp_inside_str = f"{temp_inside:.1f}°C" if temp_inside is not None else "N/A"
                temp_target_str = f"{temp_target:.1f}°C" if temp_target is not None else "N/A"
                
                st.markdown(f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {temp_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🌡️ Температура</h4>
                    <h2 style="margin: 8px 0; color: {temp_color};">{temp_inside_str}</h2>
                    <small style="color: #8b949e;">Цель: {temp_target_str}</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                humidity = data.get('humidity', 0)
                if humidity is None:
                    humidity = 0
                humidity_color = get_status_color(humidity, 40, 70)
                humidity_str = f"{humidity:.1f}%" if humidity is not None else "N/A"
                
                st.markdown(f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {humidity_color};">
                    <h4 style="margin: 0; color: #e6edf3;">💧 Влажность</h4>
                    <h2 style="margin: 8px 0; color: {humidity_color};">{humidity_str}</h2>
                    <small style="color: #8b949e;">Норма: 40-70%</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                co2 = data.get('co2', 0)
                if co2 is None:
                    co2 = 0
                co2_color = get_status_color(co2, 400, 800)
                co2_str = f"{co2} ppm" if co2 is not None else "N/A"
                
                st.markdown(f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {co2_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🫁 CO₂</h4>
                    <h2 style="margin: 8px 0; color: {co2_color};">{co2_str}</h2>
                    <small style="color: #8b949e;">Норма: 400-3000 ppm</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                ventilation = data.get('ventilation_level', 0)
                if ventilation is None:
                    ventilation = 0
                vent_color = "#58a6ff"
                ventilation_str = f"{ventilation}%" if ventilation is not None else "N/A"
                
                st.markdown(f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {vent_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🌀 Вентиляция</h4>
                    <h2 style="margin: 8px 0; color: {vent_color};">{ventilation_str}</h2>
                    <small style="color: #8b949e;">Уровень мощности</small>
                </div>
                """, unsafe_allow_html=True)
            
            # Дополнительные параметры
            st.subheader("📊 Дополнительные параметры")
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                pressure = data.get('pressure', 0)
                pressure_str = f"{pressure:.1f} Па" if pressure is not None else "N/A"
                st.markdown(
                    '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🌪️ Давление</div>',
                    unsafe_allow_html=True
                )
                st.metric(label="", value=pressure_str, help="Отрицательное давление", label_visibility="collapsed")
            
            with col6:
                nh3 = data.get('nh3', 0)
                nh3_str = f"{nh3:.1f} ppm" if nh3 is not None else "N/A"
                st.markdown(
                    '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">💨 NH₃</div>',
                    unsafe_allow_html=True
                )
                st.metric(label="", value=nh3_str, help="Концентрация аммиака", label_visibility="collapsed")
            
            with col7:
                st.markdown(
                    '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">💻 Версия ПО</div>',
                    unsafe_allow_html=True
                )
                st.metric(label="", value=data.get('software_version', '–'), help="Версия прошивки контроллера", label_visibility="collapsed")
            
            with col8:
                last_update = data.get('timestamp', datetime.now())
                st.markdown(
                    '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🕐 Обновлено</div>',
                    unsafe_allow_html=True
                )
                st.metric(label="", value=last_update.strftime("%H:%M:%S"), help="Время последнего обновления", label_visibility="collapsed")
            
            # Статистика работы (если доступна)
            if DEVICE_AVAILABLE:
                try:
                    stats = get_statistics()
                    if stats:
                        st.subheader("📈 Статистика работы")
                        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
                        
                        with col_stats1:
                            st.markdown(
                                '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">✅ Успешных</div>',
                                unsafe_allow_html=True
                            )
                            st.metric(label="", value=stats.get('success_count', 0), label_visibility="collapsed")
                        
                        with col_stats2:
                            st.markdown(
                                '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">❌ Ошибок</div>',
                                unsafe_allow_html=True
                            )
                            st.metric(label="", value=stats.get('error_count', 0), label_visibility="collapsed")
                        
                        with col_stats3:
                            success_rate = stats.get('success_rate', 0) * 100
                            st.markdown(
                                '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">📊 Успешность</div>',
                                unsafe_allow_html=True
                            )
                            st.metric(label="", value=f"{success_rate:.1f}%", label_visibility="collapsed")
                        
                        with col_stats4:
                            is_running = stats.get('is_running', False)
                            status = "🟢 Работает" if is_running else "🔴 Остановлен"
                            st.markdown(
                                '<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🔄 Статус</div>',
                                unsafe_allow_html=True
                            )
                            st.metric(label="", value=status, label_visibility="collapsed")
                except Exception as e:
                    st.warning(f"⚠️ Не удалось получить статистику: {e}")
            
            # Графики с историческими данными
            st.subheader("📈 Исторические графики")
            
            try:
                # Получаем исторические данные из БД
                historical_data = get_historical_data(hours=history_hours)
                
                if historical_data and len(historical_data) > 1:
                    # Преобразуем в DataFrame
                    df = pd.DataFrame(historical_data)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    
                    st.info(f"📊 Показано {len(historical_data)} записей за последние {history_hours} часов из базы данных")
                    
                else:
                    st.warning("⚠️ Недостаточно исторических данных для построения графиков.")
                    st.info("💡 Попробуйте увеличить количество часов в боковой панели")
                    historical_data = None
                    
            except Exception as e:
                st.error(f"❌ Ошибка получения исторических данных: {e}")
                historical_data = None
                
            if historical_data and len(historical_data) > 1:
                # График температуры
                col_temp, col_hum = st.columns(2)
                
                with col_temp:
                    fig_temp = go.Figure()
                    
                    # Фильтруем данные температуры (убираем None)
                    temp_data = df[df['temp_inside'].notna()].copy()
                    if not temp_data.empty:
                        fig_temp.add_trace(go.Scatter(
                            x=temp_data['timestamp'], 
                            y=temp_data['temp_inside'],
                            mode='lines+markers',
                            name='Текущая',
                            line=dict(color='#58a6ff', width=2),
                            connectgaps=False  # Не соединяем пропуски
                        ))
                    
                    # Добавляем целевую температуру если есть данные
                    target_data = df[df['temp_target'].notna()].copy()
                    if not target_data.empty:
                        fig_temp.add_trace(go.Scatter(
                            x=target_data['timestamp'], 
                            y=target_data['temp_target'],
                            mode='lines',
                            name='Целевая',
                            line=dict(color='#f85149', width=1, dash='dash'),
                            connectgaps=False
                        ))
                    
                    fig_temp.update_layout(
                        title="🌡️ Температура",
                        xaxis_title="Время",
                        yaxis_title="°C",
                        template="plotly_dark",
                        height=300
                    )
                    st.plotly_chart(fig_temp, use_container_width=True)
                
                with col_hum:
                    # Фильтруем данные влажности
                    humidity_data = df[df['humidity'].notna()].copy()
                    if not humidity_data.empty:
                        fig_hum = go.Figure()
                        fig_hum.add_trace(go.Scatter(
                            x=humidity_data['timestamp'], 
                            y=humidity_data['humidity'],
                            mode='lines+markers',
                            name='Влажность',
                            line=dict(color='#7c3aed', width=2),
                            connectgaps=False
                        ))
                        
                        fig_hum.update_layout(
                            title="💧 Влажность",
                            xaxis_title="Время",
                            yaxis_title="%",
                            template="plotly_dark",
                            height=300
                        )
                        st.plotly_chart(fig_hum, use_container_width=True)
                    else:
                        st.info("📊 График влажности недоступен (нет данных за выбранный период)")
                
                # График CO2 и вентиляции
                col_co2, col_vent = st.columns(2)
                
                with col_co2:
                    # Фильтруем данные CO2
                    co2_data = df[df['co2'].notna()].copy()
                    if not co2_data.empty:
                        fig_co2 = go.Figure()
                        fig_co2.add_trace(go.Scatter(
                            x=co2_data['timestamp'], 
                            y=co2_data['co2'],
                            mode='lines+markers',
                            name='CO₂',
                            line=dict(color='#f85149', width=2),
                            connectgaps=False
                        ))
                        
                        fig_co2.update_layout(
                            title="🫁 Концентрация CO₂",
                            xaxis_title="Время",
                            yaxis_title="ppm",
                            template="plotly_dark",
                            height=300
                        )
                        st.plotly_chart(fig_co2, use_container_width=True)
                    else:
                        st.info("📊 График CO₂ недоступен (нет данных за выбранный период)")
                
                with col_vent:
                    # Фильтруем данные вентиляции
                    vent_data = df[df['ventilation_level'].notna()].copy()
                    if not vent_data.empty:
                        fig_vent = go.Figure()
                        fig_vent.add_trace(go.Scatter(
                            x=vent_data['timestamp'], 
                            y=vent_data['ventilation_level'],
                            mode='lines+markers',
                            name='Вентиляция',
                            line=dict(color='#56d364', width=2),
                            connectgaps=False
                        ))
                        
                        fig_vent.update_layout(
                            title="🌀 Уровень вентиляции",
                            xaxis_title="Время",
                            yaxis_title="%",
                            template="plotly_dark",
                            height=300
                        )
                        st.plotly_chart(fig_vent, use_container_width=True)
                    else:
                        st.info("📊 График вентиляции недоступен (нет данных за выбранный период)")
        
        # Проверяем нужно ли автообновление
        if not auto_refresh:
            break
            
        time.sleep(refresh_interval)

if __name__ == "__main__":
    main()