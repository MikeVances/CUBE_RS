"""
Dashboard Reader для КУБ-1063 - ИСПРАВЛЕННАЯ ВЕРСИЯ
Специальные функции для дашборда с кэшированием и статистикой
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from threading import Lock

# Добавляем корневую директорию проекта в путь (как в app.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Безопасные импорты с fallback
try:
    from modbus.modbus_storage import read_data
except ImportError:
    try:
        from .modbus_storage import read_data
    except ImportError:
        # Fallback для прямого запуска
        import modbus_storage
        read_data = modbus_storage.read_data

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DashboardReader:
    """Читатель с кэшированием для дашборда"""
    
    def __init__(self):
        self.cache = {}
        self.cache_time = {}
        self.cache_duration = 2  # сократил до 2 секунд для более частого обновления
        self.lock = Lock()
        self.stats = {
            'success_count': 0,
            'error_count': 0,
            'last_success': None,
            'last_error': None,
            'is_running': True
        }
    
    def read_all(self) -> Dict[str, Any]:
        """Чтение всех данных с кэшированием из SQLite БД"""
        with self.lock:
            current_time = time.time()
            
            # Проверяем кэш (сократил время кэширования)
            if (self.cache and 
                current_time - self.cache_time.get('timestamp', 0) < self.cache_duration):
                logger.debug("📋 Возвращаем данные из кэша")
                return self.cache.copy()
            
            try:
                # Читаем данные из SQLite БД (заполняется gateway1)
                logger.debug("🔄 Читаем данные из БД...")
                data = read_data()
                
                # Проверяем что данные есть и свежие
                if data and self._is_data_valid(data):
                    self.stats['success_count'] += 1
                    self.stats['last_success'] = datetime.now()
                    data['connection_status'] = 'connected'
                    
                    # Кэшируем результат
                    self.cache = data
                    self.cache_time['timestamp'] = current_time
                    
                    logger.debug(f"✅ Данные обновлены: temp={data.get('temp_inside')}°C")
                    return data
                    
                else:
                    self.stats['error_count'] += 1
                    self.stats['last_error'] = datetime.now()
                    
                    # Если нет свежих данных, возвращаем старые из кэша с пометкой
                    if self.cache:
                        logger.warning("⚠️ Нет свежих данных, возвращаем кэш")
                        cache_copy = self.cache.copy()
                        cache_copy['connection_status'] = 'stale_data'
                        return cache_copy
                    else:
                        logger.warning("⚠️ Нет данных в БД")
                        return {
                            'timestamp': datetime.now(),
                            'connection_status': 'no_data',
                            'error': 'Нет данных в БД'
                        }
                
            except Exception as e:
                logger.error(f"❌ Ошибка чтения данных: {e}")
                self.stats['error_count'] += 1
                self.stats['last_error'] = datetime.now()
                
                # Возвращаем кэш если есть
                if self.cache:
                    logger.warning("⚠️ Ошибка БД, возвращаем кэш")
                    cache_copy = self.cache.copy()
                    cache_copy['connection_status'] = 'error'
                    return cache_copy
                else:
                    return {
                        'timestamp': datetime.now(),
                        'connection_status': 'error',
                        'error': str(e)
                    }
    
    def _is_data_valid(self, data: Dict[str, Any]) -> bool:
        """Проверка что данные валидны и свежие"""
        if not data:
            return False
            
        # Проверяем наличие ключевых полей
        if data.get('temp_inside') is None:
            logger.warning("⚠️ Нет данных температуры")
            return False
            
        # Проверяем свежесть данных
        updated_at = data.get('updated_at')
        if updated_at:
            try:
                if isinstance(updated_at, str):
                    # Обрабатываем разные форматы времени
                    update_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                elif hasattr(updated_at, 'strftime'):
                    # Если это уже datetime объект
                    update_time = updated_at
                else:
                    logger.warning("⚠️ Неизвестный формат времени обновления")
                    return True  # Считаем валидным если не можем проверить
                
                now = datetime.now()
                age_seconds = (now - update_time).total_seconds()
                
                # Данные считаем свежими если им меньше 30 секунд
                if age_seconds > 30:
                    logger.warning(f"⚠️ Данные устарели: {age_seconds:.0f}с назад")
                    return False
                    
            except Exception as e:
                logger.warning(f"⚠️ Не могу проверить время обновления: {e}")
                # Если не можем проверить время, считаем данные валидными
                return True
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики работы"""
        with self.lock:
            total_attempts = self.stats['success_count'] + self.stats['error_count']
            success_rate = (self.stats['success_count'] / total_attempts 
                          if total_attempts > 0 else 0)
            
            return {
                'success_count': self.stats['success_count'],
                'error_count': self.stats['error_count'],
                'success_rate': success_rate,
                'is_running': self.stats['is_running'],
                'last_success': self.stats['last_success'],
                'last_error': self.stats['last_error'],
                'cache_age': time.time() - self.cache_time.get('timestamp', 0) if self.cache else None
            }
    
    def clear_cache(self):
        """Очистка кэша (для принудительного обновления)"""
        with self.lock:
            self.cache = {}
            self.cache_time = {}
            logger.info("🧹 Кэш очищен")
    
    def stop(self):
        """Остановка читателя"""
        with self.lock:
            self.stats['is_running'] = False

# Глобальный экземпляр
_dashboard_reader = DashboardReader()

def get_dashboard_reader() -> DashboardReader:
    """Получение глобального экземпляра читателя"""
    return _dashboard_reader

def read_all() -> Dict[str, Any]:
    """Основная функция для чтения данных"""
    return _dashboard_reader.read_all()

def get_statistics() -> Dict[str, Any]:
    """Получение статистики"""
    return _dashboard_reader.get_statistics()

def clear_cache():
    """Очистка кэша"""
    _dashboard_reader.clear_cache()

def test_dashboard_reader():
    """Тест dashboard reader"""
    print("🔍 Тестирование ИСПРАВЛЕННОГО Dashboard Reader")
    print("=" * 50)
    
    # Очищаем кэш для свежих данных
    clear_cache()
    
    data = read_all()
    print("📊 Данные:")
    for key, value in data.items():
        if key != 'timestamp':
            print(f"  {key}: {value}")
    
    stats = get_statistics()
    print("\n📈 Статистика:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n🔍 Путь поиска модулей:")
    for i, path in enumerate(sys.path[:3]):
        print(f"  {i}: {path}")

if __name__ == "__main__":
    test_dashboard_reader()