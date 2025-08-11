"""
Streamlit Dashboard для КУБ-1063
Визуализация данных с контроллера в стиле Grafana (БЕЗ ГРАФИКОВ)
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import time
from datetime import datetime, timedelta

# Импорт функции чтения данных
try:
    from dashboard.dashboard_reader import read_all, get_statistics
    DEVICE_AVAILABLE = True
except ImportError:
    try:
        from .dashboard_reader import read_all, get_statistics
        DEVICE_AVAILABLE = True
    except ImportError:
        st.error("❌ Не удалось импортировать dashboard_reader")
        DEVICE_AVAILABLE = False
        
        def read_all():
            return {'temp_inside': 25.0, 'humidity': 60.0, 'co2': 400, 'connection_status': 'demo'}
        
        def get_statistics():
            return {'success_count': 0, 'error_count': 0, 'success_rate': 0, 'is_running': False}

# Настройка страницы
st.set_page_config(
    page_title="КУБ-1063 Dashboard", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Стили в стиле Grafana
st.markdown("""
    <style>
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    
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
    
    h1, h2, h3 {
        color: #58a6ff !important;
    }
    
    .element-container {
        background-color: #21262d;
        border-radius: 6px;
        margin: 8px 0;
    }
    </style>
""", unsafe_allow_html=True)

def get_status_color(value, min_val, max_val):
    """Определяет цвет статуса на основе значения"""
    if value is None:
        return "#6c757d"
    if min_val <= value <= max_val:
        return "#28a745"  # Зеленый
    elif abs(value - min_val) < abs(value - max_val):
        return "#ffc107"  # Желтый
    else:
        return "#dc3545"  # Красный

def main():
    st.title("📊 Панель мониторинга КУБ-1063")
    
    # Боковая панель с настройками
    with st.sidebar:
        st.header("⚙️ Настройки")
        auto_refresh = st.checkbox("Автообновление", value=True)
        refresh_interval = st.slider("Интервал обновления (сек)", 1, 60, 5)
        
        st.header("🔌 Статус системы")
        if DEVICE_AVAILABLE:
            st.success("✅ Dashboard Reader подключен")
        else:
            st.error("❌ Dashboard Reader недоступен")
        
        if st.button("🔄 Принудительное обновление"):
            st.rerun()
    
    # Создаем placeholder для автообновления
    placeholder = st.empty()
    
    # Основной цикл обновления
    while True:
        with placeholder.container():
            # Получаем данные
            try:
                data = read_all()
                if not data:
                    st.error("❌ Нет данных с контроллера")
                    data = {}
            except Exception as e:
                st.error(f"❌ Ошибка чтения данных: {e}")
                data = {}
            
            # Показываем статус подключения
            connection_status = data.get('connection_status', 'unknown')
            if connection_status == 'connected':
                st.success("🟢 Подключение к КУБ-1063 активно")
            elif connection_status == 'demo':
                st.info("🔵 Демо режим (нет подключения к устройству)")
            else:
                st.warning(f"⚠️ Статус подключения: {connection_status}")
            
            # Основные метрики
            st.subheader("🎯 Основные параметры")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                temp_inside = data.get('temp_inside', 0) or 0
                temp_target = data.get('temp_target', 25) or 25
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
                humidity = data.get('humidity', 0) or 0
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
                co2 = data.get('co2', 0) or 0
                co2_color = get_status_color(co2, 400, 3000)
                co2_str = f"{co2} ppm" if co2 is not None else "N/A"
                
                st.markdown(f"""
                <div style="background-color: #21262d; padding: 16px; border-radius: 6px; border-left: 4px solid {co2_color};">
                    <h4 style="margin: 0; color: #e6edf3;">🫁 CO₂</h4>
                    <h2 style="margin: 8px 0; color: {co2_color};">{co2_str}</h2>
                    <small style="color: #8b949e;">Норма: 400-3000 ppm</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                ventilation = data.get('ventilation_level', 0) or 0
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
                st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🌪️ Давление</div>', unsafe_allow_html=True)
                st.metric(label="Давление", value=pressure_str, help="Отрицательное давление", label_visibility="collapsed")
            
            with col6:
                nh3 = data.get('nh3', 0)
                nh3_str = f"{nh3:.1f} ppm" if nh3 is not None else "N/A"
                st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">💨 NH₃</div>', unsafe_allow_html=True)
                st.metric(label="NH3", value=nh3_str, help="Концентрация аммиака", label_visibility="collapsed")
            
            with col7:
                st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">💻 Версия ПО</div>', unsafe_allow_html=True)
                st.metric(label="Версия ПО", value=data.get('software_version', '–'), help="Версия прошивки контроллера", label_visibility="collapsed")
            
            with col8:
                last_update = data.get('timestamp', datetime.now())
                if isinstance(last_update, str):
                    try:
                        last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    except:
                        last_update = datetime.now()
                
                st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🕐 Обновлено</div>', unsafe_allow_html=True)
                st.metric(label="Время", value=last_update.strftime("%H:%M:%S"), help="Время последнего обновления", label_visibility="collapsed")
            
            # Статистика работы
            if DEVICE_AVAILABLE:
                try:
                    stats = get_statistics()
                    if stats:
                        st.subheader("📈 Статистика работы")
                        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
                        
                        with col_stats1:
                            st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">✅ Успешных</div>', unsafe_allow_html=True)
                            st.metric(label="Успешных", value=stats.get('success_count', 0), label_visibility="collapsed")
                        
                        with col_stats2:
                            st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">❌ Ошибок</div>', unsafe_allow_html=True)
                            st.metric(label="Ошибок", value=stats.get('error_count', 0), label_visibility="collapsed")
                        
                        with col_stats3:
                            success_rate = stats.get('success_rate', 0) * 100
                            st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">📊 Успешность</div>', unsafe_allow_html=True)
                            st.metric(label="Успешность", value=f"{success_rate:.1f}%", label_visibility="collapsed")
                        
                        with col_stats4:
                            is_running = stats.get('is_running', False)
                            status = "🟢 Работает" if is_running else "🔴 Остановлен"
                            st.markdown('<div style="font-size:1.3em; color:#fff; font-weight:bold; margin-bottom:0.2em;">🔄 Статус</div>', unsafe_allow_html=True)
                            st.metric(label="Статус", value=status, label_visibility="collapsed")
                except Exception as e:
                    st.warning(f"⚠️ Не удалось получить статистику: {e}")
            
            # Заметка о графиках
            st.subheader("📈 Графики")
            st.info("📊 Графики временно отключены. Планируется реализация на базе SQL с историей данных.")
        
        # Проверяем нужно ли автообновление
        if not auto_refresh:
            break
            
        time.sleep(refresh_interval)

if __name__ == "__main__":
    main()