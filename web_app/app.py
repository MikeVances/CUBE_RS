#!/usr/bin/env python3
"""
Flask Web Application для мониторинга КУБ-1063
Получает данные от Gateway через защищенный API
Поддерживает интеграцию с Tailscale для управления mesh-сетью
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
import asyncio
from typing import Optional, Dict, Any

# Добавляем пути для импорта core модулей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Импорт Tailscale интеграции
from tailscale_integration import (
    get_tailscale_service, 
    get_tailscale_config, 
    cleanup_tailscale_service
)

# Импорт системы регистрации устройств
from device_registry import get_device_registry

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

@app.route('/tailscale')
def tailscale_dashboard():
    """Страница управления Tailscale"""
    return render_template('tailscale_dashboard.html')

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
    tailscale_config = get_tailscale_config()
    
    return jsonify({
        'status': 'healthy',
        'service': 'kub-1063-web-app',
        'timestamp': datetime.now().isoformat(),
        'api_configured': api_config.is_configured(),
        'tailscale_configured': tailscale_config.is_configured()
    })

# === Tailscale Integration Routes ===

def run_async_route(coro):
    """Helper для запуска async функций в sync Flask routes"""
    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)

@app.route('/api/tailscale/status')
def tailscale_status():
    """Получение статуса Tailscale mesh-сети"""
    service = get_tailscale_service()
    config = get_tailscale_config()
    
    if not service:
        return jsonify({
            'status': 'disabled',
            'message': 'Tailscale не настроен',
            'config': config.get_config_status()
        }), 200
    
    try:
        status = run_async_route(service.get_tailnet_status())
        return jsonify(status)
    except Exception as e:
        logger.error(f"Ошибка получения статуса Tailscale: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tailscale/devices')
def tailscale_devices():
    """Получение списка устройств в Tailscale mesh-сети"""
    service = get_tailscale_service()
    if not service:
        return jsonify({
            'status': 'error',
            'message': 'Tailscale не настроен'
        }), 503
    
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    try:
        devices = run_async_route(service.get_devices_list(force_refresh))
        return jsonify({
            'status': 'success',
            'devices': devices,
            'total': len(devices),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка получения устройств Tailscale: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tailscale/farms')
def tailscale_farms():
    """Получение списка ферм в Tailscale mesh-сети"""
    service = get_tailscale_service()
    if not service:
        return jsonify({
            'status': 'error',
            'message': 'Tailscale не настроен'
        }), 503
    
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    try:
        farms = run_async_route(service.get_farms_list(force_refresh))
        return jsonify({
            'status': 'success',
            'farms': farms,
            'total': len(farms),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка получения ферм Tailscale: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tailscale/devices/<device_id>')
def tailscale_device_details(device_id):
    """Получение детальной информации об устройстве"""
    service = get_tailscale_service()
    if not service:
        return jsonify({
            'status': 'error',
            'message': 'Tailscale не настроен'
        }), 503
    
    try:
        details = run_async_route(service.get_device_details(device_id))
        return jsonify(details)
    except Exception as e:
        logger.error(f"Ошибка получения деталей устройства {device_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tailscale/auth-key', methods=['POST'])
def create_tailscale_auth_key():
    """Создание ключа авторизации для новой фермы"""
    service = get_tailscale_service()
    if not service:
        return jsonify({
            'status': 'error',
            'message': 'Tailscale не настроен'
        }), 503
    
    data = request.get_json() or {}
    ephemeral = data.get('ephemeral', False)
    reusable = data.get('reusable', True)
    
    try:
        result = run_async_route(
            service.create_farm_auth_key(ephemeral=ephemeral, reusable=reusable)
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Ошибка создания auth key: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tailscale/connectivity/check', methods=['POST'])
def check_farm_connectivity():
    """Проверка подключения к ферме"""
    service = get_tailscale_service()
    if not service:
        return jsonify({
            'status': 'error',
            'message': 'Tailscale не настроен'
        }), 503
    
    data = request.get_json()
    if not data or 'tailscale_ip' not in data:
        return jsonify({
            'status': 'error',
            'message': 'Требуется tailscale_ip'
        }), 400
    
    tailscale_ip = data['tailscale_ip']
    api_port = data.get('api_port', 8080)
    
    try:
        result = run_async_route(
            service.check_farm_connectivity(tailscale_ip, api_port)
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Ошибка проверки подключения: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# === Device Registry Routes ===

@app.route('/api/registry/auth-key', methods=['POST'])
def create_registry_auth_key():
    """Создание ключа авторизации для регистрации устройства"""
    registry = get_device_registry()
    
    data = request.get_json() or {}
    expires_hours = data.get('expires_hours', 24)
    max_usage = data.get('max_usage', -1)  # -1 = unlimited
    is_reusable = data.get('is_reusable', True)
    is_ephemeral = data.get('is_ephemeral', False)
    tags = data.get('tags', ['farm'])
    created_by = data.get('created_by', 'web-admin')
    
    try:
        auth_key = registry.generate_auth_key(
            expires_hours=expires_hours,
            max_usage=max_usage,
            is_reusable=is_reusable,
            is_ephemeral=is_ephemeral,
            tags=tags,
            created_by=created_by
        )
        
        return jsonify({
            'status': 'success',
            'auth_key': auth_key,
            'expires_hours': expires_hours,
            'max_usage': max_usage,
            'is_reusable': is_reusable,
            'is_ephemeral': is_ephemeral,
            'tags': tags,
            'created_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка создания registry auth key: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/register', methods=['POST'])
def register_device():
    """Регистрация нового устройства"""
    registry = get_device_registry()
    
    data = request.get_json()
    if not data:
        return jsonify({
            'status': 'error',
            'message': 'Отсутствуют данные запроса'
        }), 400
    
    required_fields = ['auth_key', 'device_hostname', 'device_type', 'device_info']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'status': 'error',
                'message': f'Отсутствует обязательное поле: {field}'
            }), 400
    
    try:
        request_id = registry.create_registration_request(
            auth_key=data['auth_key'],
            device_hostname=data['device_hostname'],
            device_type=data['device_type'],
            device_info=data['device_info'],
            tailscale_ip=data.get('tailscale_ip', '')
        )
        
        # Автоматическое одобрение для простоты (в production можно добавить ручное одобрение)
        auto_approve = data.get('auto_approve', True)
        if auto_approve:
            approved = registry.approve_registration_request(
                request_id=request_id,
                approved_by='auto-system',
                additional_metadata=data.get('additional_metadata', {})
            )
            
            if approved:
                return jsonify({
                    'status': 'success',
                    'message': 'Устройство зарегистрировано и активировано',
                    'request_id': request_id,
                    'auto_approved': True
                })
        
        return jsonify({
            'status': 'success',
            'message': 'Запрос на регистрацию создан',
            'request_id': request_id,
            'auto_approved': False
        })
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Ошибка регистрации устройства: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Внутренняя ошибка сервера'
        }), 500

@app.route('/api/registry/devices')
def get_registry_devices():
    """Получение списка зарегистрированных устройств"""
    registry = get_device_registry()
    
    device_type = request.args.get('type')
    status = request.args.get('status')
    
    try:
        devices = registry.get_registered_devices(device_type=device_type, status=status)
        
        devices_data = []
        for device in devices:
            device_dict = {
                'device_id': device.device_id,
                'hostname': device.hostname,
                'tailscale_ip': device.tailscale_ip,
                'registration_time': device.registration_time,
                'last_seen': device.last_seen,
                'status': device.status,
                'device_type': device.device_type,
                'metadata': device.metadata,
                'tags': device.tags,
                'owner_email': device.owner_email,
                'notes': device.notes
            }
            devices_data.append(device_dict)
        
        return jsonify({
            'status': 'success',
            'devices': devices_data,
            'total': len(devices_data),
            'filters': {
                'type': device_type,
                'status': status
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения устройств из реестра: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/requests')
def get_registration_requests():
    """Получение ожидающих одобрения запросов регистрации"""
    registry = get_device_registry()
    
    try:
        requests = registry.get_pending_registration_requests()
        
        requests_data = []
        for req in requests:
            req_dict = {
                'request_id': req.request_id,
                'device_hostname': req.device_hostname,
                'device_type': req.device_type,
                'device_info': req.device_info,
                'requested_time': req.requested_time,
                'tailscale_ip': req.tailscale_ip,
                'status': req.status
            }
            requests_data.append(req_dict)
        
        return jsonify({
            'status': 'success',
            'requests': requests_data,
            'total': len(requests_data),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения запросов регистрации: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/requests/<request_id>/approve', methods=['POST'])
def approve_registration_request(request_id):
    """Одобрение запроса на регистрацию"""
    registry = get_device_registry()
    
    data = request.get_json() or {}
    approved_by = data.get('approved_by', 'web-admin')
    additional_metadata = data.get('additional_metadata', {})
    
    try:
        success = registry.approve_registration_request(
            request_id=request_id,
            approved_by=approved_by,
            additional_metadata=additional_metadata
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Запрос одобрен, устройство активировано',
                'request_id': request_id
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Запрос не найден или уже обработан'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка одобрения запроса {request_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/devices/<device_id>/revoke', methods=['POST'])
def revoke_device(device_id):
    """Отзыв устройства из системы"""
    registry = get_device_registry()
    
    data = request.get_json() or {}
    reason = data.get('reason', 'Отзыв администратором')
    
    try:
        success = registry.revoke_device(device_id=device_id, reason=reason)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Устройство отозвано',
                'device_id': device_id,
                'reason': reason
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Устройство не найдено'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка отзыва устройства {device_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/devices/<device_id>/heartbeat', methods=['POST'])
def device_heartbeat(device_id):
    """Обновление времени последней активности устройства"""
    registry = get_device_registry()
    
    data = request.get_json() or {}
    tailscale_ip = data.get('tailscale_ip')
    
    try:
        success = registry.update_device_last_seen(
            device_id=device_id,
            tailscale_ip=tailscale_ip
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Heartbeat обновлен',
                'device_id': device_id,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Устройство не найдено'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка heartbeat для {device_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/registry/stats')
def get_registry_stats():
    """Получение статистики реестра устройств"""
    registry = get_device_registry()
    
    try:
        stats = registry.get_device_stats()
        return jsonify({
            'status': 'success',
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики реестра: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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
    
    # Проверяем конфигурацию Tailscale
    tailscale_config = get_tailscale_config()
    if not tailscale_config.is_configured():
        logger.warning("⚠️ Tailscale не настроен! Для активации установите переменные окружения:")
        logger.warning("   - TAILSCALE_ENABLED=true")
        logger.warning("   - TAILSCALE_TAILNET=your-tailnet.ts.net")
        logger.warning("   - TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx")
    else:
        logger.info("✅ Tailscale настроен, tailnet: %s", tailscale_config.tailnet)
    
    # Cleanup handler при завершении
    import atexit
    atexit.register(lambda: asyncio.run(cleanup_tailscale_service()))
    
    # Запуск в dev режиме
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')