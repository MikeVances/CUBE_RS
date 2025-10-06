#!/usr/bin/env python3
"""
CUBE RS Mobile App API - Extended Routes
Дополнительные API endpoints для работы с фермами и устройствами
"""

from flask import jsonify, request
import requests
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def setup_extended_api(app, SERVER_URL, get_jwt_token, validate_jwt_token, require_auth, require_permission):
    """Настройка расширенных API маршрутов"""
    
    # ========================
    # Farm & Device API Routes  
    # ========================
    
    @app.route('/api/farms')
    @require_auth
    @require_permission('farm:view')
    def api_farms():
        """Список ферм пользователя"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{SERVER_URL}/api/farms', headers=headers, timeout=10)
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(response.json()), response.status_code
                
        except Exception as e:
            logger.error(f"Farms API error: {e}")
            return jsonify({'error': 'Failed to fetch farms'}), 500
    
    @app.route('/api/farms/<farm_id>/devices')
    @require_auth
    @require_permission('device:view')
    def api_farm_devices(farm_id):
        """Список устройств фермы"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{SERVER_URL}/api/farms/{farm_id}/devices', headers=headers, timeout=10)
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(response.json()), response.status_code
                
        except Exception as e:
            logger.error(f"Farm devices API error: {e}")
            return jsonify({'error': 'Failed to fetch farm devices'}), 500
    
    @app.route('/api/devices/<device_id>/data')
    @require_auth
    @require_permission('device:view')
    def api_device_data(device_id):
        """Текущие данные устройства"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            # Параметры запроса
            params = {}
            if request.args.get('period'):
                params['period'] = request.args.get('period')
            if request.args.get('variables'):
                params['variables'] = request.args.get('variables')
            
            response = requests.get(
                f'{SERVER_URL}/api/devices/{device_id}/data',
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(response.json()), response.status_code
                
        except Exception as e:
            logger.error(f"Device data API error: {e}")
            return jsonify({'error': 'Failed to fetch device data'}), 500
    
    @app.route('/api/devices/<device_id>/history')
    @require_auth  
    @require_permission('device:view')
    def api_device_history(device_id):
        """История данных устройства"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            # Параметры запроса
            params = {}
            if request.args.get('start_date'):
                params['start_date'] = request.args.get('start_date')
            if request.args.get('end_date'):
                params['end_date'] = request.args.get('end_date')
            if request.args.get('interval'):
                params['interval'] = request.args.get('interval')
            
            response = requests.get(
                f'{SERVER_URL}/api/devices/{device_id}/history',
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(response.json()), response.status_code
                
        except Exception as e:
            logger.error(f"Device history API error: {e}")
            return jsonify({'error': 'Failed to fetch device history'}), 500
    
    # ========================
    # Real-time Data Routes
    # ========================
    
    @app.route('/api/realtime/status')
    @require_auth
    def api_realtime_status():
        """Статус всех доступных устройств в реальном времени"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{SERVER_URL}/api/realtime/status', headers=headers, timeout=5)
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify({'error': 'Failed to get realtime status'}), response.status_code
                
        except Exception as e:
            logger.error(f"Realtime status error: {e}")
            return jsonify({'error': 'Connection error'}), 500
    
    @app.route('/api/tunnel/connect', methods=['POST'])
    @require_auth
    @require_permission('tunnel:connect')
    def api_tunnel_connect():
        """Запрос P2P туннеля к EDGE устройству"""
        data = request.get_json()
        target_device_id = data.get('device_id')
        
        if not target_device_id:
            return jsonify({'error': 'Device ID required'}), 400
        
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.post(
                f'{SERVER_URL}/api/tunnel/connect',
                headers=headers,
                json={'target_device_id': target_device_id},
                timeout=30
            )
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(response.json()), response.status_code
                
        except Exception as e:
            logger.error(f"Tunnel connect error: {e}")
            return jsonify({'error': 'Failed to establish tunnel'}), 500
    
    @app.route('/api/system/status')
    @require_auth
    def api_system_status():
        """Системная информация"""
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{SERVER_URL}/api/system/status', headers=headers, timeout=10)
            
            if response.status_code == 200:
                server_status = response.json()
            else:
                server_status = {'error': 'Server unavailable'}
            
            return jsonify({
                'app_status': 'running',
                'app_version': '1.0.0',
                'server_status': server_status,
                'user_role': request.user['role'],
                'permissions': request.user['permissions']
            })
            
        except Exception as e:
            logger.error(f"System status error: {e}")
            return jsonify({
                'app_status': 'running',
                'app_version': '1.0.0',
                'server_status': {'error': str(e)},
                'user_role': request.user['role'],
                'permissions': request.user['permissions']
            }), 500