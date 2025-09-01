#!/usr/bin/env python3
"""
Flask Web Application для мониторинга КУБ-1063
Получает данные от Gateway через защищенный API
"""

import os
import sys
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_cors import CORS
import logging
import requests
from datetime import datetime, timedelta
import hashlib
import hmac
import time
from typing import Optional, Dict, Any

# Добавляем пути для импорта core модулей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app)

# Конфигурация API
class APIConfig:
    """Конфигурация для подключения к Gateway API"""
    
    def __init__(self):
        # URL Gateway API (задается через переменную окружения)
        self.gateway_url = os.environ.get('GATEWAY_URL', 'http://localhost:8000')
        # API ключ для аутентификации
        self.api_key = os.environ.get('API_KEY', '')
        # API секрет для HMAC подписи
        self.api_secret = os.environ.get('API_SECRET', '')
        # Таймаут запросов
        self.timeout = int(os.environ.get('API_TIMEOUT', '10'))
    
    def is_configured(self) -> bool:
        """Проверяет, настроен ли API"""
        return bool(self.api_key and self.api_secret and self.gateway_url)

api_config = APIConfig()

def generate_signature(payload: str, timestamp: str) -> str:
    """Генерирует HMAC подпись для API запроса"""
    message = f"{timestamp}{payload}"
    signature = hmac.new(
        api_config.api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def make_api_request(endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Optional[Dict]:
    """Выполняет защищенный API запрос к Gateway"""
    if not api_config.is_configured():
        logger.error("API не настроен - отсутствуют ключи или URL")
        return None
    
    try:
        url = f"{api_config.gateway_url.rstrip('/')}/{endpoint.lstrip('/')}"
        timestamp = str(int(time.time()))
        payload = ''
        
        if data and method.upper() in ['POST', 'PUT']:
            import json
            payload = json.dumps(data)
        
        signature = generate_signature(payload, timestamp)
        
        headers = {
            'X-API-Key': api_config.api_key,
            'X-Timestamp': timestamp,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=api_config.timeout)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=api_config.timeout)
        else:
            logger.error(f"Неподдерживаемый HTTP метод: {method}")
            return None
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.Timeout:
        logger.error(f"Таймаут API запроса к {endpoint}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Ошибка подключения к API {endpoint}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP ошибка API {endpoint}: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка API {endpoint}: {e}")
        return None

@app.route('/')
def index():
    """Главная страница дашборда"""
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """Проверка статуса API подключения"""
    if not api_config.is_configured():
        return jsonify({
            'status': 'error',
            'message': 'API не настроен',
            'configured': False
        }), 500
    
    # Пробуем подключиться к Gateway
    result = make_api_request('/api/health')
    if result:
        return jsonify({
            'status': 'ok',
            'message': 'Подключение к Gateway установлено',
            'configured': True,
            'gateway_status': result
        })
    else:
        return jsonify({
            'status': 'error', 
            'message': 'Не удается подключиться к Gateway',
            'configured': True
        }), 503

@app.route('/api/data/current')
def get_current_data():
    """Получение текущих данных КУБ-1063"""
    data = make_api_request('/api/data/current')
    
    if data:
        return jsonify({
            'status': 'success',
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Не удалось получить данные'
        }), 503

@app.route('/api/data/history')
def get_history_data():
    """Получение исторических данных"""
    hours = request.args.get('hours', 6, type=int)
    hours = min(max(hours, 1), 168)  # Ограничиваем 1-168 часов (неделя)
    
    data = make_api_request(f'/api/data/history?hours={hours}')
    
    if data:
        return jsonify({
            'status': 'success',
            'data': data,
            'hours': hours,
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Не удалось получить исторические данные'
        }), 503

@app.route('/api/data/statistics')
def get_statistics():
    """Получение статистики работы системы"""
    data = make_api_request('/api/data/statistics')
    
    if data:
        return jsonify({
            'status': 'success',
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Не удалось получить статистику'
        }), 503

@app.route('/health')
def health_check():
    """Health check для Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'kub-1063-web-app',
        'timestamp': datetime.now().isoformat(),
        'api_configured': api_config.is_configured()
    })

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Страница не найдена'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

if __name__ == '__main__':
    # Проверяем конфигурацию при запуске
    if not api_config.is_configured():
        logger.warning("⚠️ API не настроен! Установите переменные окружения:")
        logger.warning("   - GATEWAY_URL: URL вашего Gateway API")
        logger.warning("   - API_KEY: Ключ для аутентификации") 
        logger.warning("   - API_SECRET: Секрет для HMAC подписи")
    else:
        logger.info("✅ API настроен, Gateway URL: %s", api_config.gateway_url)
    
    # Запуск в dev режиме
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')