#!/usr/bin/env python3
"""
Remote Dashboard API для EDGE системы
HTTP API для удаленного доступа через Tailscale VPN
Предоставляет тот же функционал что и Telegram бот, но через HTTP
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

from core.device_registry import get_device_registry, DeviceType
from core.config_manager import get_config
from core.device_adapters import get_device_adapter
from core.log_filter import get_secure_logger

logger = get_secure_logger(__name__)


class RemoteDashboardAPI:
    """
    HTTP API для удаленного дашборда
    Предоставляет те же данные что и Telegram бот, но через REST API
    """
    
    def __init__(self):
        self.app = Flask(__name__)
        config = get_config()
        security = getattr(config, "security", None)
        cors_origins: List[str]
        if security and getattr(security, "cors_allowed_origins", None):
            origins_setting = security.cors_allowed_origins
            if isinstance(origins_setting, str):
                cors_origins = [origins_setting]
            else:
                cors_origins = list(origins_setting)
        else:
            cors_origins = ["http://localhost", "http://127.0.0.1"]

        CORS(
            self.app,
            resources={r"/*": {"origins": cors_origins}},
            supports_credentials=False,
        )
        self.registry = get_device_registry()
        self._setup_routes()
        
        logger.info("🌐 Remote Dashboard API инициализирован")
    
    def _setup_routes(self):
        """Настройка HTTP маршрутов"""
        
        @self.app.route('/')
        def index():
            """Главная страница дашборда"""
            return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>EDGE Remote Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .device { border: 1px solid #ccc; margin: 10px; padding: 15px; border-radius: 5px; }
        .status-ok { background-color: #d4edda; }
        .status-warning { background-color: #fff3cd; }
        .status-error { background-color: #f8d7da; }
        .refresh-btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>🏭 EDGE Remote Dashboard</h1>
    <p>Удаленный мониторинг КУБ устройств через Tailscale</p>
    
    <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
    
    <div id="devices">Загрузка данных...</div>
    
    <script>
    async function loadDevices() {
        try {
            const response = await fetch('/api/devices/status');
            const data = await response.json();
            
            let html = '<h2>📊 Статус устройств:</h2>';
            
            data.devices.forEach(device => {
                const statusClass = device.has_issues ? 'status-error' : 'status-ok';
                html += `
                    <div class="device ${statusClass}">
                        <h3>${device.name} (${device.device_type})</h3>
                        <p><strong>Местоположение:</strong> ${device.location || 'Не указано'}</p>
                        <p><strong>Статус:</strong> ${device.enabled ? '✅ Активно' : '❌ Отключено'}</p>
                        <p><strong>Последнее обновление:</strong> ${new Date(device.last_update * 1000).toLocaleString()}</p>
                    </div>
                `;
            });
            
            document.getElementById('devices').innerHTML = html;
        } catch (error) {
            document.getElementById('devices').innerHTML = '❌ Ошибка загрузки данных: ' + error;
        }
    }
    
    loadDevices();
    </script>
</body>
</html>
            """)
        
        @self.app.route('/api/health')
        def health():
            """Проверка работоспособности API"""
            return jsonify({
                "status": "healthy",
                "service": "EDGE Remote Dashboard",
                "timestamp": time.time(),
                "version": "2.0"
            })
        
        @self.app.route('/api/devices')
        def get_devices():
            """Список всех устройств (аналог /devices в боте)"""
            try:
                devices = self.registry.get_all_devices(enabled_only=False)
                
                devices_data = []
                for device in devices:
                    devices_data.append({
                        "device_id": device.device_id,
                        "device_type": device.device_type.value,
                        "slave_id": device.slave_id,
                        "name": device.name,
                        "description": device.description,
                        "location": device.location,
                        "enabled": device.enabled
                    })
                
                return jsonify({
                    "success": True,
                    "count": len(devices_data),
                    "devices": devices_data
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка API /devices: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @self.app.route('/api/devices/status')
        def get_devices_status():
            """Статус всех устройств с данными (аналог /status в боте)"""
            try:
                devices = self.registry.get_all_devices(enabled_only=True)
                
                devices_data = []
                total_issues = 0
                
                for device in devices:
                    try:
                        adapter = get_device_adapter(device.device_type)
                        if not adapter:
                            continue
                        
                        device_manager = adapter.create_device_manager(device.device_id)
                        
                        # TODO: Здесь нужно получить актуальные данные с устройства
                        # Пока используем заглушку
                        
                        # Получаем аварии и предупреждения
                        alarms = adapter.get_critical_alarms(device_manager)
                        warnings = adapter.get_warnings(device_manager)
                        has_issues = len(alarms) > 0 or len(warnings) > 0
                        
                        if has_issues:
                            total_issues += 1
                        
                        devices_data.append({
                            "device_id": device.device_id,
                            "device_type": device.device_type.value,
                            "name": device.name,
                            "location": device.location,
                            "enabled": device.enabled,
                            "has_issues": has_issues,
                            "alarms": alarms,
                            "warnings": warnings,
                            "last_update": time.time()
                        })
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка получения статуса устройства {device.device_id}: {e}")
                        devices_data.append({
                            "device_id": device.device_id,
                            "name": device.name,
                            "status": "error",
                            "error": str(e),
                            "has_issues": True,
                            "last_update": time.time()
                        })
                        total_issues += 1
                
                return jsonify({
                    "success": True,
                    "timestamp": time.time(),
                    "summary": {
                        "total_devices": len(devices),
                        "online_devices": len(devices) - total_issues,
                        "offline_devices": 0,  # TODO: реализовать определение offline
                        "devices_with_issues": total_issues
                    },
                    "devices": devices_data
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка API /devices/status: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @self.app.route('/api/device/<int:device_id>')
        def get_device_details(device_id):
            """Подробные данные устройства (аналог /device_N в боте)"""
            try:
                device = self.registry.get_device(device_id)
                if not device:
                    return jsonify({"success": False, "error": "Device not found"}), 404
                
                adapter = get_device_adapter(device.device_type)
                if not adapter:
                    return jsonify({"success": False, "error": "Adapter not available"}), 500
                
                device_manager = adapter.create_device_manager(device_id)
                
                # Получаем форматированный текст (как в боте)
                formatted_text = adapter.format_for_display(device_manager)
                
                # Получаем аварии и предупреждения
                alarms = adapter.get_critical_alarms(device_manager)
                warnings = adapter.get_warnings(device_manager)
                
                # TODO: Получить актуальные значения переменных
                variables = {}  # Заглушка
                
                return jsonify({
                    "success": True,
                    "device": {
                        "device_id": device.device_id,
                        "device_type": device.device_type.value,
                        "slave_id": device.slave_id,
                        "name": device.name,
                        "description": device.description,
                        "location": device.location,
                        "enabled": device.enabled
                    },
                    "data": {
                        "formatted_text": formatted_text,
                        "variables": variables,
                        "alarms": alarms,
                        "warnings": warnings,
                        "timestamp": time.time()
                    }
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка API /device/{device_id}: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @self.app.route('/api/alarms')
        def get_all_alarms():
            """Все активные аварии (аналог /alarms в боте)"""
            try:
                devices = self.registry.get_all_devices(enabled_only=True)
                all_alarms = []
                
                for device in devices:
                    try:
                        adapter = get_device_adapter(device.device_type)
                        if not adapter:
                            continue
                        
                        device_manager = adapter.create_device_manager(device.device_id)
                        alarms = adapter.get_critical_alarms(device_manager)
                        warnings = adapter.get_warnings(device_manager)
                        
                        if alarms or warnings:
                            all_alarms.append({
                                "device_id": device.device_id,
                                "device_name": device.name,
                                "device_type": device.device_type.value,
                                "location": device.location,
                                "alarms": alarms,
                                "warnings": warnings,
                                "timestamp": time.time()
                            })
                    
                    except Exception as e:
                        logger.error(f"❌ Ошибка получения аварий устройства {device.device_id}: {e}")
                
                return jsonify({
                    "success": True,
                    "count": len(all_alarms),
                    "alarms": all_alarms,
                    "timestamp": time.time()
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка API /alarms: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @self.app.route('/api/types')
        def get_device_types():
            """Список поддерживаемых типов устройств"""
            try:
                types_data = []
                for device_type in DeviceType:
                    if device_type != DeviceType.UNKNOWN:
                        adapter = get_device_adapter(device_type)
                        types_data.append({
                            "type": device_type.value,
                            "available": adapter is not None,
                            "description": self._get_type_description(device_type)
                        })
                
                return jsonify({
                    "success": True,
                    "types": types_data
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка API /types: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
    
    def _get_type_description(self, device_type: DeviceType) -> str:
        """Описание типа устройства"""
        descriptions = {
            DeviceType.KUB_1063: "Система вентиляции и климат-контроля",
            DeviceType.KUB_1112: "Система обогрева и управления горелками"
        }
        return descriptions.get(device_type, "Неизвестный тип устройства")
    
    def run(self, host: str = '0.0.0.0', port: int = 8080, debug: bool = False):
        """Запуск Flask приложения"""
        logger.info(f"🚀 Запуск Remote Dashboard API на {host}:{port}")
        logger.info("   📊 Доступные endpoints:")
        logger.info("   • GET / - веб интерфейс дашборда")  
        logger.info("   • GET /api/health - проверка состояния")
        logger.info("   • GET /api/devices - список устройств")
        logger.info("   • GET /api/devices/status - статус всех устройств")
        logger.info("   • GET /api/device/<id> - детали устройства")
        logger.info("   • GET /api/alarms - активные аварии")
        logger.info("   • GET /api/types - типы устройств")
        
        self.app.run(host=host, port=port, debug=debug)


# Глобальный экземпляр API
_dashboard_api: Optional[RemoteDashboardAPI] = None


def get_dashboard_api() -> RemoteDashboardAPI:
    """Получение глобального экземпляра Dashboard API"""
    global _dashboard_api
    if _dashboard_api is None:
        _dashboard_api = RemoteDashboardAPI()
    return _dashboard_api
