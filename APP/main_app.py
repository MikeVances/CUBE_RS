#!/usr/bin/env python3
"""
CUBE RS Mobile App Backend
Центральный API для мобильного приложения и веб-интерфейса с защитой от MITM атак
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import requests
import jwt as pyjwt
from functools import wraps

# Импортируем MITM защиту для APP
from security import create_mitm_protected_client, SecurityError

# Конфигурация
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'development-secret-key-change-in-production')

# CORS для мобильных приложений
CORS(app, origins=[
    "http://localhost:3000",  # React Native Metro
    "http://10.0.2.2:3000",  # Android Emulator
    "https://your-app.com"    # Production mobile app
])

# Конфигурация SERVER
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:8080')
TUNNEL_BROKER_URL = os.getenv('TUNNEL_BROKER_URL', SERVER_URL)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================
# Authentication Helpers
# ========================

def get_jwt_token():
    """Получение JWT токена из заголовков или сессии"""
    # Проверяем Authorization header для мобильного приложения
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    # Проверяем сессию для веб-интерфейса
    return session.get('jwt_token')

def validate_jwt_token(token):
    """Проверка JWT токена через SERVER"""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f'{SERVER_URL}/api/auth/validate', headers=headers, timeout=5)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        logger.error(f"JWT validation error: {e}")
        return None

def require_auth(f):
    """Декоратор для требования аутентификации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_jwt_token()
        if not token:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            else:
                return redirect(url_for('login'))
        
        user_info = validate_jwt_token(token)
        if not user_info:
            if request.is_json:
                return jsonify({'error': 'Invalid token'}), 401
            else:
                session.pop('jwt_token', None)
                return redirect(url_for('login'))
        
        # Добавляем информацию о пользователе в request
        request.user = user_info
        return f(*args, **kwargs)
    
    return decorated_function

def require_permission(permission):
    """Декоратор для проверки разрешений"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_permissions = request.user.get('permissions', [])
            if permission not in user_permissions and '*' not in user_permissions:
                return jsonify({'error': f'Permission denied: {permission}'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ========================
# Web Interface Routes
# ========================

@app.route('/')
def index():
    """Главная страница веб-интерфейса"""
    token = get_jwt_token()
    if not token:
        return redirect(url_for('login'))
    
    user_info = validate_jwt_token(token)
    if not user_info:
        session.pop('jwt_token', None)
        return redirect(url_for('login'))
    
    return render_template('index.html', user=user_info)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('mobile_login.html', error='Username and password required')
        
        # Аутентификация через SERVER
        try:
            response = requests.post(f'{SERVER_URL}/api/auth/login', json={
                'username': username,
                'password': password
            }, timeout=10)
            
            if response.status_code == 200:
                auth_data = response.json()
                session['jwt_token'] = auth_data['token']
                return redirect(url_for('index'))
            else:
                error_msg = response.json().get('error', 'Login failed')
                return render_template('mobile_login.html', error=error_msg)
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return render_template('mobile_login.html', error='Server connection error')
    
    return render_template('mobile_login.html')

@app.route('/logout')
def logout():
    """Выход из системы"""
    session.pop('jwt_token', None)
    return redirect(url_for('login'))

# ========================
# Mobile API Routes
# ========================

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API аутентификации для мобильного приложения"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    try:
        # Проксируем запрос на SERVER
        response = requests.post(f'{SERVER_URL}/api/auth/login', json=data, timeout=10)
        
        if response.status_code == 200:
            auth_data = response.json()
            return jsonify({
                'token': auth_data['token'],
                'user': auth_data['user'],
                'expires_in': auth_data.get('expires_in', 3600)
            })
        else:
            return jsonify(response.json()), response.status_code
            
    except Exception as e:
        logger.error(f"API login error: {e}")
        return jsonify({'error': 'Server connection error'}), 500

@app.route('/api/auth/refresh', methods=['POST'])
@require_auth
def api_refresh_token():
    """Обновление JWT токена"""
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.post(f'{SERVER_URL}/api/auth/refresh', headers=headers, timeout=10)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify(response.json()), response.status_code
            
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({'error': 'Token refresh failed'}), 500

@app.route('/api/user/profile')
@require_auth
def api_user_profile():
    """Профиль пользователя"""
    return jsonify({
        'user_id': request.user['user_id'],
        'username': request.user['username'],
        'email': request.user.get('email'),
        'role': request.user['role'],
        'permissions': request.user['permissions']
    })

# ========================
# Подключение расширенных API
# ========================

from api import setup_extended_api
setup_extended_api(app, SERVER_URL, get_jwt_token, validate_jwt_token, require_auth, require_permission)

# ========================
# Health & Monitoring
# ========================

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Проверяем связь с SERVER
        response = requests.get(f'{SERVER_URL}/health', timeout=5)
        server_healthy = response.status_code == 200
    except:
        server_healthy = False
    
    return jsonify({
        'status': 'healthy' if server_healthy else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'app_version': '1.0.0',
        'server_connection': server_healthy,
        'server_url': SERVER_URL
    }), 200 if server_healthy else 503

# ========================
# Error Handlers
# ========================

@app.errorhandler(404)
def not_found(error):
    if request.is_json:
        return jsonify({'error': 'API endpoint not found'}), 404
    else:
        return render_template('index.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    if request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    else:
        return render_template('index.html', error='Internal server error'), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"🚀 Starting CUBE RS Mobile App Backend on port {port}")
    logger.info(f"📡 SERVER URL: {SERVER_URL}")
    logger.info(f"🔒 Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)