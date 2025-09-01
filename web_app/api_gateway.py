#!/usr/bin/env python3
"""
API Gateway для предоставления данных КУБ-1063 внешним приложениям
Работает локально и предоставляет защищенный API
"""

import os
import sys
from flask import Flask, jsonify, request, abort
from flask_cors import CORS
import logging
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
import json

# Добавляем пути для импорта модулей системы
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from dashboard.dashboard_reader import read_all, get_historical_data, get_statistics, test_connection
    from core.config_manager import get_config
    from core.security_manager import SecurityManager
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)
CORS(app, origins=["*"])  # В продакшене ограничить домены

# Загрузка конфигурации
try:
    config = get_config()
    security_manager = SecurityManager()
except Exception as e:
    logger.error(f"Ошибка загрузки конфигурации: {e}")
    config = None
    security_manager = None

class APIAuth:
    """Система аутентификации API"""
    
    def __init__(self):
        self.api_keys = {}
        self.load_api_keys()
    
    def load_api_keys(self):
        """Загружает API ключи из конфигурации"""
        try:
            if security_manager:
                # Пробуем загрузить API ключи из зашифрованного конфига
                api_config = security_manager.load_encrypted_config('api_keys')
                if api_config:
                    self.api_keys = api_config
                    logger.info(f"✅ Загружено {len(self.api_keys)} API ключей")
                else:
                    # Создаем дефолтный набор ключей для разработки
                    self.create_default_keys()
            else:
                self.create_default_keys()
        except Exception as e:
            logger.error(f"Ошибка загрузки API ключей: {e}")
            self.create_default_keys()
    
    def create_default_keys(self):
        """Создает ключи по умолчанию для разработки"""
        import secrets
        
        default_key = "dev-api-key"
        default_secret = secrets.token_hex(32)
        
        self.api_keys = {
            default_key: {
                'secret': default_secret,
                'name': 'Development Key',
                'permissions': ['read'],
                'created': time.time()
            }
        }
        
        # Сохраняем ключи
        if security_manager:
            try:
                security_manager.save_encrypted_config('api_keys', self.api_keys)
                logger.info("✅ API ключи сохранены в зашифрованном виде")
            except Exception as e:
                logger.error(f"Ошибка сохранения API ключей: {e}")
        
        logger.warning("⚠️ Используются ключи разработки!")
        logger.info(f"🔑 API Key: {default_key}")
        logger.info(f"🔐 API Secret: {default_secret}")
    
    def verify_request(self, api_key: str, timestamp: str, signature: str, payload: str) -> bool:
        """Проверяет подпись API запроса"""
        if api_key not in self.api_keys:
            logger.warning(f"Неизвестный API ключ: {api_key}")
            return False
        
        # Проверяем timestamp (не старше 5 минут)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:  # 5 минут
                logger.warning("Запрос слишком старый")
                return False
        except ValueError:
            logger.warning("Неверный формат timestamp")
            return False
        
        # Проверяем подпись
        secret = self.api_keys[api_key]['secret']
        expected_signature = self.generate_signature(payload, timestamp, secret)
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Неверная подпись запроса")
            return False
        
        return True
    
    def generate_signature(self, payload: str, timestamp: str, secret: str) -> str:
        """Генерирует HMAC подпись"""
        message = f"{timestamp}{payload}"
        return hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

# Инициализация аутентификации
auth = APIAuth()

def require_auth(f):
    """Декоратор для проверки аутентификации"""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        timestamp = request.headers.get('X-Timestamp')
        signature = request.headers.get('X-Signature')
        
        if not all([api_key, timestamp, signature]):
            logger.warning("Отсутствуют заголовки аутентификации")
            abort(401, description="Отсутствуют заголовки аутентификации")
        
        # Получаем payload
        if request.method in ['POST', 'PUT', 'PATCH']:
            payload = request.get_data(as_text=True) or ''
        else:
            payload = ''
        
        if not auth.verify_request(api_key, timestamp, signature, payload):
            abort(403, description="Неверная аутентификация")
        
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/api/health')
@require_auth
def health_check():
    """Проверка состояния API"""
    db_status = test_connection()
    
    return jsonify({
        'status': 'healthy' if db_status else 'degraded',
        'service': 'kub-1063-api-gateway',
        'database': 'connected' if db_status else 'disconnected',
        'timestamp': time.time()
    })

@app.route('/api/data/current')
@require_auth
def get_current_data():
    """Получение текущих данных КУБ-1063"""
    try:
        data = read_all()
        
        if data:
            # Преобразуем datetime в ISO формат для JSON
            if 'timestamp' in data:
                data['timestamp'] = data['timestamp'].isoformat()
            
            return jsonify({
                'status': 'success',
                'data': data,
                'retrieved_at': time.time()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Нет доступных данных'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка получения текущих данных: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Внутренняя ошибка сервера'
        }), 500

@app.route('/api/data/history')
@require_auth
def get_history():
    """Получение исторических данных"""
    try:
        hours = request.args.get('hours', 6, type=int)
        hours = min(max(hours, 1), 168)  # Ограничиваем 1-168 часов
        
        data = get_historical_data(hours)
        
        if data:
            # Преобразуем datetime объекты в ISO формат
            formatted_data = []
            for record in data:
                formatted_record = {}
                for key, value in record.items():
                    if hasattr(value, 'isoformat'):  # datetime объект
                        formatted_record[key] = value.isoformat()
                    else:
                        formatted_record[key] = value
                formatted_data.append(formatted_record)
            
            return jsonify({
                'status': 'success',
                'data': formatted_data,
                'hours': hours,
                'count': len(formatted_data),
                'retrieved_at': time.time()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Нет исторических данных'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка получения исторических данных: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Внутренняя ошибка сервера'
        }), 500

@app.route('/api/data/statistics')
@require_auth
def get_stats():
    """Получение статистики системы"""
    try:
        data = get_statistics()
        
        if data:
            return jsonify({
                'status': 'success',
                'data': data,
                'retrieved_at': time.time()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Нет статистических данных'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Внутренняя ошибка сервера'
        }), 500

@app.route('/api/keys/info')
@require_auth
def get_api_info():
    """Информация об API ключе (без секрета)"""
    api_key = request.headers.get('X-API-Key')
    if api_key in auth.api_keys:
        key_info = auth.api_keys[api_key].copy()
        key_info.pop('secret', None)  # Удаляем секрет из ответа
        
        return jsonify({
            'status': 'success',
            'key_info': key_info
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Ключ не найден'
        }), 404

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Неавторизованный доступ', 'message': str(error.description)}), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({'error': 'Доступ запрещен', 'message': str(error.description)}), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Не найдено'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

if __name__ == '__main__':
    logger.info("🚀 Запуск API Gateway для КУБ-1063")
    logger.info(f"🔑 Загружено API ключей: {len(auth.api_keys)}")
    
    # Запуск сервера
    port = int(os.environ.get('API_PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)