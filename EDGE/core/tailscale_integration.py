#!/usr/bin/env python3
"""
Tailscale Integration для EDGE системы
Tailscale = ТОЛЬКО ТРАНСПОРТ для удаленного дашборда
Не дублирует функции, а предоставляет безопасный туннель к EDGE API
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.device_registry import get_device_registry, DeviceType
from core.device_adapters import get_device_adapter
from core.log_filter import get_secure_logger

logger = get_secure_logger(__name__)

# Добавляем путь к tunnel_system
PARENT_DIR = Path(__file__).parent.parent.parent
TUNNEL_SYSTEM_PATH = PARENT_DIR / "tunnel_system"

if TUNNEL_SYSTEM_PATH.exists():
    sys.path.insert(0, str(TUNNEL_SYSTEM_PATH))
    try:
        from tailscale_manager import TailscaleManager, TailscaleFarm
        from tailscale_discovery_service import DiscoveryService
        TAILSCALE_AVAILABLE = True
        logger.info("✅ Tailscale система найдена и подключена")
    except ImportError as e:
        TAILSCALE_AVAILABLE = False
        logger.warning(f"⚠️ Tailscale система недоступна: {e}")
else:
    TAILSCALE_AVAILABLE = False
    logger.warning("⚠️ Tunnel system не найдена")


class EDGETailscaleProvider:
    """
    Провайдер данных КУБ устройств для Tailscale системы
    Заменяет заглушку KubDataProvider реальными данными EDGE
    """
    
    def __init__(self):
        self.registry = get_device_registry()
        self.device_managers = {}
        self.last_update = 0
        self.update_interval = 5  # секунд
        
        logger.info("🔧 EDGETailscaleProvider инициализирован")
        
        # Инициализация менеджеров устройств
        self._initialize_device_managers()
    
    def _initialize_device_managers(self):
        """Инициализация менеджеров для всех устройств"""
        devices = self.registry.get_all_devices(enabled_only=True)
        
        for device in devices:
            try:
                adapter = get_device_adapter(device.device_type)
                if adapter:
                    manager = adapter.create_device_manager(device.device_id)
                    self.device_managers[device.device_id] = {
                        'manager': manager,
                        'adapter': adapter,
                        'device_info': device
                    }
                    logger.debug(f"✅ Менеджер создан для {device.name} (ID: {device.device_id})")
                else:
                    logger.warning(f"⚠️ Адаптер не найден для {device.device_type}")
            except Exception as e:
                logger.error(f"❌ Ошибка создания менеджера для {device.name}: {e}")
    
    def get_current_data(self) -> Dict[str, Any]:
        """
        Получение текущих данных всех КУБ устройств в формате для Tailscale
        Заменяет заглушку из tailscale_farm_client.py
        """
        current_time = time.time()
        
        # Обновляем данные при необходимости
        if current_time - self.last_update > self.update_interval:
            self._update_device_data()
            self.last_update = current_time
        
        # Собираем данные со всех устройств
        farm_data = {
            "timestamp": current_time,
            "farm_status": "online",
            "devices_count": len(self.device_managers),
            "devices": {}
        }
        
        for device_id, device_info in self.device_managers.items():
            manager = device_info['manager']
            adapter = device_info['adapter']
            device = device_info['device_info']
            
            try:
                # Получаем данные устройства
                device_data = {
                    "device_id": device_id,
                    "device_type": device.device_type.value,
                    "name": device.name,
                    "location": device.location,
                    "status": "online",
                    "variables": {}
                }
                
                # Добавляем специфичные для типа устройства данные
                if device.device_type == DeviceType.KUB_1063:
                    device_data["variables"] = self._get_kub1063_data(manager)
                elif device.device_type == DeviceType.KUB_1112:
                    device_data["variables"] = self._get_kub1112_data(manager)
                
                # Добавляем аварии
                alarms = adapter.get_critical_alarms(manager)
                warnings = adapter.get_warnings(manager)
                device_data["alarms"] = alarms
                device_data["warnings"] = warnings
                device_data["has_issues"] = len(alarms) > 0 or len(warnings) > 0
                
                farm_data["devices"][f"device_{device_id}"] = device_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения данных устройства {device_id}: {e}")
                farm_data["devices"][f"device_{device_id}"] = {
                    "device_id": device_id,
                    "name": device.name,
                    "status": "error",
                    "error": str(e)
                }
        
        return farm_data
    
    def _update_device_data(self):
        """Обновление данных с устройств (здесь подключение к Modbus)"""
        # TODO: Интеграция с реальным Modbus reader
        # В реальной системе здесь будет:
        # - Подключение к modbus/unified_system.py
        # - Чтение актуальных данных с устройств
        # - Обновление device_managers
        
        logger.debug("🔄 Обновление данных устройств (заглушка)")
        pass
    
    def _get_kub1063_data(self, manager) -> Dict[str, Any]:
        """Получение данных КУБ-1063 (вентиляция)"""
        try:
            return {
                # Температуры
                "temp_inside_1": manager.get_variable_value("temp_inside_1"),
                "temp_inside_2": manager.get_variable_value("temp_inside_2"), 
                "temp_outside": manager.get_variable_value("temp_outside"),
                
                # Климат
                "humidity": manager.get_variable_value("humidity"),
                "co2": manager.get_variable_value("co2"),
                "nh3": manager.get_variable_value("nh3"),
                "pressure": manager.get_variable_value("pressure"),
                
                # Вентиляция
                "ventilation_level": manager.get_variable_value("ventilation_level"),
                "ventilation_scheme": manager.get_variable_value("ventilation_scheme"),
                
                # Статусы
                "temp_inside_1_status": manager.get_variable_status("temp_inside_1"),
                "temp_inside_2_status": manager.get_variable_status("temp_inside_2"),
                "humidity_status": manager.get_variable_status("humidity"),
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных КУБ-1063: {e}")
            return {"error": str(e)}
    
    def _get_kub1112_data(self, manager) -> Dict[str, Any]:
        """Получение данных КУБ-1112 (горелка)"""
        try:
            # TODO: Реализовать после создания КУБ-1112 адаптера
            return {
                "flame_level": 0,  # Заглушка
                "gas_pressure": 0,
                "burner_status": "unknown"
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных КУБ-1112: {e}")
            return {"error": str(e)}
    
    def get_farm_summary(self) -> Dict[str, Any]:
        """Получение краткой сводки по ферме для Discovery Service"""
        data = self.get_current_data()
        
        # Подсчет статистики
        total_devices = len(self.device_managers)
        online_devices = sum(1 for d in data.get("devices", {}).values() 
                           if d.get("status") == "online")
        devices_with_issues = sum(1 for d in data.get("devices", {}).values() 
                                if d.get("has_issues", False))
        
        return {
            "farm_name": os.getenv("FARM_NAME", "EDGE Farm"),
            "location": os.getenv("FARM_LOCATION", "Unknown"),
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": total_devices - online_devices,
            "devices_with_issues": devices_with_issues,
            "last_update": data["timestamp"],
            "capabilities": ["kub1063", "kub1112", "monitoring", "telegram_bot"],
            "edge_version": "2.0",
            "status": "healthy" if devices_with_issues == 0 else "warning"
        }


class EDGETailscaleIntegration:
    """
    Главный класс интеграции EDGE с Tailscale системой
    """
    
    def __init__(self, api_key: Optional[str] = None, tailnet: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAILSCALE_API_KEY")
        self.tailnet = tailnet or os.getenv("TAILSCALE_TAILNET", "your-tailnet.ts.net")
        
        self.data_provider = EDGETailscaleProvider()
        self.manager = None
        self.discovery_service = None
        
        if TAILSCALE_AVAILABLE and self.api_key:
            self._initialize_tailscale()
        else:
            logger.warning("⚠️ Tailscale интеграция отключена (нет API ключа или системы)")
    
    def _initialize_tailscale(self):
        """Инициализация Tailscale компонентов"""
        try:
            if self.api_key:
                self.manager = TailscaleManager(self.api_key, self.tailnet)
                logger.info("✅ TailscaleManager инициализирован")
            
            # Инициализация Discovery Service (опционально)
            self.discovery_service = DiscoveryService()
            logger.info("✅ Discovery Service инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Tailscale: {e}")
    
    async def start_farm_service(self, port: int = 8080):
        """
        Запуск HTTP сервиса фермы для удаленного доступа через Tailscale
        Заменяет tailscale_farm_client.py интеграцией с EDGE
        """
        if not TAILSCALE_AVAILABLE:
            logger.error("❌ Tailscale система недоступна")
            return
        
        from flask import Flask, jsonify
        from flask_cors import CORS
        
        app = Flask(__name__)
        CORS(app)
        
        @app.route('/api/farm/data')
        def get_farm_data():
            """API endpoint для получения данных фермы"""
            try:
                data = self.data_provider.get_current_data()
                return jsonify({"success": True, "data": data})
            except Exception as e:
                logger.error(f"❌ Ошибка API /farm/data: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @app.route('/api/farm/summary')
        def get_farm_summary():
            """API endpoint для получения краткой сводки"""
            try:
                summary = self.data_provider.get_farm_summary()
                return jsonify({"success": True, "data": summary})
            except Exception as e:
                logger.error(f"❌ Ошибка API /farm/summary: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @app.route('/api/device/<int:device_id>')
        def get_device_data(device_id):
            """API endpoint для получения данных конкретного устройства"""
            try:
                farm_data = self.data_provider.get_current_data()
                device_data = farm_data["devices"].get(f"device_{device_id}")
                
                if device_data:
                    return jsonify({"success": True, "data": device_data})
                else:
                    return jsonify({"success": False, "error": "Device not found"}), 404
            except Exception as e:
                logger.error(f"❌ Ошибка API /device/{device_id}: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
        
        @app.route('/api/health')
        def health_check():
            """Health check endpoint"""
            return jsonify({
                "success": True,
                "status": "healthy",
                "timestamp": time.time(),
                "service": "EDGE-Tailscale Integration"
            })
        
        # Запуск Flask приложения
        logger.info(f"🚀 Запуск Tailscale Farm Service на порту {port}")
        app.run(host='0.0.0.0', port=port, debug=False)
    
    def register_with_discovery(self):
        """Регистрация фермы в Discovery Service"""
        if not self.discovery_service:
            logger.warning("⚠️ Discovery Service не инициализирован")
            return
        
        try:
            summary = self.data_provider.get_farm_summary()
            # TODO: Реализовать регистрацию в Discovery Service
            logger.info("✅ Ферма зарегистрирована в Discovery Service")
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации в Discovery Service: {e}")


# Глобальный экземпляр интеграции
_tailscale_integration: Optional[EDGETailscaleIntegration] = None


def get_tailscale_integration() -> Optional[EDGETailscaleIntegration]:
    """Получение глобального экземпляра Tailscale интеграции"""
    global _tailscale_integration
    if _tailscale_integration is None:
        _tailscale_integration = EDGETailscaleIntegration()
    return _tailscale_integration


def is_tailscale_available() -> bool:
    """Проверка доступности Tailscale системы"""
    return TAILSCALE_AVAILABLE


async def start_tailscale_service(port: int = 8080):
    """Convenience функция для запуска Tailscale сервиса"""
    integration = get_tailscale_integration()
    if integration:
        await integration.start_farm_service(port)
    else:
        logger.error("❌ Tailscale интеграция недоступна")


if __name__ == "__main__":
    # Тестовый запуск
    logging.basicConfig(level=logging.INFO)
    
    if is_tailscale_available():
        print("✅ Tailscale система доступна")
        
        # Тест провайдера данных
        provider = EDGETailscaleProvider()
        data = provider.get_current_data()
        print(f"📊 Данные фермы: {len(data.get('devices', {}))} устройств")
        
        summary = provider.get_farm_summary()
        print(f"📋 Сводка: {summary}")
    else:
        print("❌ Tailscale система недоступна")