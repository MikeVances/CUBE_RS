#!/usr/bin/env python3
"""
Модуль для чтения данных КУБ-1063 для Dashboard
Читает данные из базы данных, заполняемой Gateway
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Добавляем корневую директорию
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from core.config_manager import get_config
    config = get_config()
    DB_PATH = config.database.file
except ImportError:
    # Fallback на стандартный путь
    DB_PATH = "kub_data.db"

logger = logging.getLogger(__name__)

def read_all() -> Optional[Dict[str, Any]]:
    """
    Читает все актуальные данные из базы данных
    
    Returns:
        dict: Словарь с данными КУБ-1063 или None при ошибке
    """
    try:
        # Подключаемся к базе данных
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Читаем последние данные из таблицы latest_data
            cursor.execute("""
                SELECT * FROM latest_data 
                WHERE id = 1
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                logger.warning("Нет данных в таблице latest_data")
                return None
            
            # Преобразуем Row в словарь
            data = dict(row)
            
            # Добавляем timestamp
            data['timestamp'] = datetime.now()
            
            # Используем значения как есть (Gateway уже обработал данные)
            result = {
                'temp_inside': data.get('temp_inside', 0) if data.get('temp_inside') else 0,
                'temp_target': data.get('temp_target', 25.0) if data.get('temp_target') else 25.0,
                'humidity': data.get('humidity', 0) if data.get('humidity') else 0,
                'co2': data.get('co2', 0) if data.get('co2') else 0,
                'nh3': data.get('nh3', 0) if data.get('nh3') else 0,
                'pressure': data.get('pressure', 0) if data.get('pressure') else 0,
                'ventilation_level': data.get('ventilation_level', 0) if data.get('ventilation_level') else 0,
                'ventilation_target': data.get('ventilation_target', 0) if data.get('ventilation_target') else 0,
                'active_alarms': data.get('active_alarms', 0) if data.get('active_alarms') else 0,
                'active_warnings': data.get('active_warnings', 0) if data.get('active_warnings') else 0,
                'software_version': _parse_software_version(data.get('software_version', 0)),
                'timestamp': data['timestamp'],
                'updated_at': data.get('updated_at', datetime.now().isoformat())
            }
            
            return result
            
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при чтении данных: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при чтении данных: {e}")
        return None

def get_historical_data(hours: int = 6) -> Optional[list]:
    """
    Получает исторические данные за указанное количество часов
    
    Args:
        hours: Количество часов истории для получения
        
    Returns:
        list: Список словарей с историческими данными или None при ошибке
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Получаем исторические данные за последние N часов
            cursor.execute("""
                SELECT 
                    timestamp,
                    temp_inside,
                    temp_target, 
                    humidity,
                    co2,
                    nh3,
                    pressure,
                    ventilation_level,
                    software_version
                FROM sensor_data 
                WHERE timestamp > datetime('now', '-{} hours')
                ORDER BY timestamp ASC
            """.format(hours))
            
            rows = cursor.fetchall()
            if not rows:
                logger.warning("Нет исторических данных за последние {} часов".format(hours))
                return []
            
            # Преобразуем данные
            historical_data = []
            for row in rows:
                data = dict(row)
                
                # Конвертируем timestamp в datetime объект
                try:
                    from datetime import datetime
                    timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                except:
                    timestamp = datetime.now()
                
                # Обрабатываем значения (используем как есть, так как Gateway уже обработал)
                record = {
                    'timestamp': timestamp,
                    'temp_inside': data.get('temp_inside') if data.get('temp_inside') is not None else None,
                    'temp_target': data.get('temp_target') if data.get('temp_target') is not None else None,
                    'humidity': data.get('humidity') if data.get('humidity') is not None else None,
                    'co2': data.get('co2') if data.get('co2') is not None else None,
                    'nh3': data.get('nh3') if data.get('nh3') is not None else None,
                    'pressure': data.get('pressure') if data.get('pressure') is not None else None,
                    'ventilation_level': data.get('ventilation_level') if data.get('ventilation_level') is not None else None,
                    'software_version': _parse_software_version(data.get('software_version'))
                }
                
                historical_data.append(record)
            
            logger.info(f"Получено {len(historical_data)} исторических записей за {hours} часов")
            return historical_data
            
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при получении исторических данных: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении исторических данных: {e}")
        return None

def get_statistics() -> Optional[Dict[str, Any]]:
    """
    Получает статистику работы системы из базы данных
    
    Returns:
        dict: Статистика работы системы
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            cursor = conn.cursor()
            
            # Получаем статистику за последние 24 часа
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_readings,
                    COUNT(CASE WHEN temp_inside > 0 THEN 1 END) as successful_readings,
                    MAX(updated_at) as last_reading,
                    MIN(updated_at) as first_reading
                FROM latest_data
                WHERE updated_at > datetime('now', '-24 hours')
            """)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            total_readings, successful_readings, last_reading, first_reading = row
            
            # Вычисляем success rate
            success_rate = (successful_readings / total_readings) if total_readings > 0 else 0
            
            # Проверяем активность системы (последнее чтение не старше 1 минуты)
            cursor.execute("""
                SELECT COUNT(*) FROM latest_data 
                WHERE updated_at > datetime('now', '-1 minute')
            """)
            recent_readings = cursor.fetchone()[0]
            is_running = recent_readings > 0
            
            return {
                'success_count': successful_readings,
                'error_count': total_readings - successful_readings,
                'total_readings': total_readings,
                'success_rate': success_rate,
                'is_running': is_running,
                'last_reading': last_reading,
                'first_reading': first_reading
            }
            
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при получении статистики: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении статистики: {e}")
        return None

def _parse_software_version(version_raw) -> str:
    """
    Парсит версию программного обеспечения из raw значения
    
    Args:
        version_raw: Сырое значение версии (int, float или str)
        
    Returns:
        str: Отформатированная версия
    """
    if not version_raw:
        return "Неизвестно"
    
    # Если уже строка - возвращаем как есть
    if isinstance(version_raw, str):
        return version_raw
    
    try:
        # Если число - пробуем распарсить
        if isinstance(version_raw, (int, float)):
            if version_raw == 0:
                return "Неизвестно"
            
            # Если целое число - считаем hex форматом
            if isinstance(version_raw, int):
                major = (version_raw >> 8) & 0xFF
                minor = version_raw & 0xFF
                return f"{major}.{minor}"
            else:
                # Если float - возвращаем как есть
                return f"{version_raw:.2f}"
        
        return str(version_raw)
        
    except Exception as e:
        return f"Ошибка: {e}"

def test_connection() -> bool:
    """
    Тестирует подключение к базе данных
    
    Returns:
        bool: True если подключение успешно
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=2.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return True
    except:
        return False

if __name__ == "__main__":
    # Тест модуля
    print("🧪 Тестирование dashboard_reader...")
    
    # Тест подключения
    if test_connection():
        print("✅ Подключение к БД: OK")
    else:
        print("❌ Подключение к БД: FAILED")
        sys.exit(1)
    
    # Тест чтения данных
    data = read_all()
    if data:
        print("✅ Чтение данных: OK")
        print(f"📊 Получено полей: {len(data)}")
        print(f"🌡️  Температура: {data.get('temp_inside', 'N/A')}°C")
        print(f"💧 Влажность: {data.get('humidity', 'N/A')}%")
        print(f"🫁 CO₂: {data.get('co2', 'N/A')} ppm")
    else:
        print("❌ Чтение данных: FAILED")
    
    # Тест статистики
    stats = get_statistics()
    if stats:
        print("✅ Статистика: OK")
        print(f"📈 Успешность: {stats.get('success_rate', 0)*100:.1f}%")
        print(f"🔄 Система активна: {stats.get('is_running', False)}")
    else:
        print("❌ Статистика: FAILED")
    
    # Тест исторических данных
    print("\n📊 Тестирование исторических данных...")
    history = get_historical_data(hours=2)
    if history:
        print(f"✅ История: OK ({len(history)} записей за 2 часа)")
        if len(history) > 0:
            first = history[0]
            last = history[-1]
            print(f"🕒 Период: {first['timestamp'].strftime('%H:%M:%S')} - {last['timestamp'].strftime('%H:%M:%S')}")
            print(f"🌡️  Диапазон температур: {min(r['temp_inside'] for r in history if r['temp_inside']):.1f}°C - {max(r['temp_inside'] for r in history if r['temp_inside']):.1f}°C")
    else:
        print("❌ История: FAILED")
    
    print("✅ Тестирование завершено!")