#!/usr/bin/env python3
"""
Интеграция EDGE Remote Dashboard с Tunnel System (IXON-style)
Обеспечивает безопасное P2P соединение пользователь <-> EDGE устройство через брокер
"""

import asyncio
import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from flask import Flask

from core.log_filter import get_secure_logger
from core.remote_dashboard import get_dashboard_api

logger = get_secure_logger(__name__)

# Добавляем путь к tunnel_system
PARENT_DIR = Path(__file__).parent.parent.parent
TUNNEL_SYSTEM_PATH = PARENT_DIR / "tunnel_system"

if TUNNEL_SYSTEM_PATH.exists():
    sys.path.insert(0, str(TUNNEL_SYSTEM_PATH))
    try:
        # Пробуем импортировать основные классы tunnel system
        from farm_client import FarmTunnelClient
        from tunnel_broker import TunnelBrokerDB, FarmInfo, UserInfo, ConnectionRequest
        TUNNEL_SYSTEM_AVAILABLE = True
        logger.info("✅ Tunnel System найдена и подключена")
    except ImportError as e:
        TUNNEL_SYSTEM_AVAILABLE = False
        logger.warning(f"⚠️ Tunnel System недоступна: {e}")
else:
    TUNNEL_SYSTEM_AVAILABLE = False
    logger.warning("⚠️ Tunnel System не найдена")


class EDGETunnelClient:
    """
    EDGE клиент для интеграции с Tunnel System
    Заменяет заглушку KubDataProvider реальными данными EDGE Remote Dashboard
    """
    
    def __init__(self, 
                 broker_url: str,
                 farm_id: str,
                 owner_id: str,
                 farm_name: str,
                 local_port: int = 8080):
        self.broker_url = broker_url.rstrip("/")
        self.farm_id = farm_id
        self.owner_id = owner_id
        self.farm_name = farm_name
        self.local_port = local_port
        
        # Получаем EDGE Remote Dashboard API
        self.dashboard_api = get_dashboard_api()
        
        # Tunnel system компоненты (если доступны)
        self.tunnel_client = None
        self.is_registered = False
        self.last_heartbeat = 0
        
        logger.info(f"🔧 EDGE Tunnel Client инициализирован для фермы: {farm_name}")
        logger.info(f"   • Farm ID: {farm_id}")
        logger.info(f"   • Owner ID: {owner_id}")
        logger.info(f"   • Broker URL: {broker_url}")
        logger.info(f"   • Local Port: {local_port}")
    
    def get_farm_capabilities(self) -> list[str]:
        """Получение capabilities фермы на основе доступных устройств"""
        try:
            # Используем EDGE Remote Dashboard для получения типов устройств
            with self.dashboard_api.app.test_client() as client:
                response = client.get('/api/types')
                if response.status_code == 200:
                    data = response.get_json()
                    capabilities = []
                    
                    for device_type in data.get('types', []):
                        if device_type.get('available'):
                            type_name = device_type['type'].lower().replace('-', '')
                            capabilities.append(type_name)
                    
                    # Добавляем базовые capabilities
                    capabilities.extend(['monitoring', 'telegram_bot', 'web_dashboard'])
                    return capabilities
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения capabilities: {e}")
        
        # Fallback capabilities
        return ['kub1063', 'monitoring', 'web_dashboard']
    
    def get_current_data(self) -> Dict[str, Any]:
        """
        Получение текущих данных всех устройств через EDGE Remote Dashboard
        Преобразует в формат совместимый с Tunnel System
        """
        try:
            with self.dashboard_api.app.test_client() as client:
                # Получаем статус всех устройств
                response = client.get('/api/devices/status')
                if response.status_code == 200:
                    edge_data = response.get_json()
                    
                    # Преобразуем в формат Tunnel System
                    tunnel_data = {
                        "timestamp": time.time(),
                        "farm_status": "online",
                        "farm_id": self.farm_id,
                        "farm_name": self.farm_name,
                        "devices_count": edge_data.get('summary', {}).get('total_devices', 0),
                        "devices_with_issues": edge_data.get('summary', {}).get('devices_with_issues', 0),
                        "devices": []
                    }
                    
                    # Добавляем данные устройств
                    for device in edge_data.get('devices', []):
                        tunnel_device = {
                            "device_id": device.get('device_id'),
                            "device_type": device.get('device_type'),
                            "name": device.get('name'),
                            "location": device.get('location'),
                            "status": "online" if not device.get('has_issues', False) else "warning",
                            "has_issues": device.get('has_issues', False),
                            "alarms": device.get('alarms', []),
                            "warnings": device.get('warnings', []),
                            "last_update": device.get('last_update', time.time())
                        }
                        tunnel_data["devices"].append(tunnel_device)
                    
                    return tunnel_data
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных EDGE: {e}")
        
        # Fallback данные
        return {
            "timestamp": time.time(),
            "farm_status": "error",
            "farm_id": self.farm_id,
            "error": "Unable to fetch EDGE data"
        }
    
    def get_device_details(self, device_id: int) -> Dict[str, Any]:
        """Получение детальных данных устройства"""
        try:
            with self.dashboard_api.app.test_client() as client:
                response = client.get(f'/api/device/{device_id}')
                if response.status_code == 200:
                    return response.get_json()
        except Exception as e:
            logger.error(f"❌ Ошибка получения деталей устройства {device_id}: {e}")
        
        return {"error": f"Device {device_id} not found"}
    
    def setup_tunnel_api_proxy(self) -> Flask:
        """
        Создание Flask приложения-прокси для интеграции с Tunnel System
        Расширяет EDGE Remote Dashboard API эндпоинтами совместимыми с Tunnel System
        """
        # Создаем новое приложение на базе существующего EDGE API
        app = Flask(__name__)
        
        # Проксируем все существующие EDGE API эндпоинты
        @app.route('/api/data/current')
        def get_current_data_tunnel():
            """Tunnel System совместимый эндпоинт для текущих данных"""
            data = self.get_current_data()
            return {
                "status": "success",
                "data": data,
                "farm_id": self.farm_id,
                "source": "edge_dashboard"
            }
        
        @app.route('/api/data/statistics')
        def get_statistics():
            """Статистика фермы для Tunnel System"""
            try:
                capabilities = self.get_farm_capabilities()
                current_data = self.get_current_data()
                
                return {
                    "status": "success",
                    "data": {
                        "farm_id": self.farm_id,
                        "farm_name": self.farm_name,
                        "capabilities": capabilities,
                        "devices_count": current_data.get("devices_count", 0),
                        "devices_with_issues": current_data.get("devices_with_issues", 0),
                        "last_update": current_data.get("timestamp", time.time()),
                        "uptime_hours": time.time() / 3600,  # Примерное время работы
                        "api_version": "edge_v2.0"
                    },
                    "farm_id": self.farm_id
                }
            except Exception as e:
                logger.error(f"❌ Ошибка получения статистики: {e}")
                return {"status": "error", "message": str(e)}, 500
        
        @app.route('/api/device/<int:device_id>')
        def get_device_tunnel(device_id):
            """Tunnel System совместимый эндпоинт для данных устройства"""
            data = self.get_device_details(device_id)
            return {
                "status": "success",
                "data": data,
                "farm_id": self.farm_id
            }
        
        @app.route('/health')
        def health():
            """Health check для Tunnel System"""
            return {
                "status": "ok",
                "service": "edge-tunnel-client",
                "farm_id": self.farm_id,
                "farm_name": self.farm_name,
                "is_registered": self.is_registered,
                "timestamp": time.time()
            }
        
        # Проксируем оригинальные EDGE эндпоинты
        @app.route('/api/edge/<path:path>')
        def proxy_to_edge(path):
            """Прокси к оригинальным EDGE API эндпоинтам"""
            try:
                with self.dashboard_api.app.test_client() as client:
                    response = client.get(f'/api/{path}')
                    return response.get_json(), response.status_code
            except Exception as e:
                return {"error": str(e)}, 500
        
        @app.route('/')
        def index():
            """Главная страница с информацией о ферме"""
            return f"""
            <h1>🏭 EDGE Farm: {self.farm_name}</h1>
            <p><strong>Farm ID:</strong> {self.farm_id}</p>
            <p><strong>Owner ID:</strong> {self.owner_id}</p>
            <p><strong>Status:</strong> {'🟢 Registered' if self.is_registered else '🔴 Not Registered'}</p>
            <p><strong>Capabilities:</strong> {', '.join(self.get_farm_capabilities())}</p>
            <hr>
            <h2>API Endpoints:</h2>
            <ul>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/api/data/current">Current Data</a></li>
                <li><a href="/api/data/statistics">Farm Statistics</a></li>
                <li><a href="/api/edge/devices">EDGE Devices</a></li>
                <li><a href="/api/edge/types">EDGE Device Types</a></li>
            </ul>
            """
        
        return app
    
    async def register_with_broker(self) -> bool:
        """Регистрация фермы в Tunnel Broker"""
        try:
            registration_data = {
                "farm_id": self.farm_id,
                "owner_id": self.owner_id,
                "farm_name": self.farm_name,
                "local_ip": self.get_local_ip(),
                "api_port": self.local_port,
                "capabilities": self.get_farm_capabilities(),
                "metadata": {
                    "api_version": "edge_v2.0",
                    "edge_version": "2.0",
                    "dashboard_type": "remote_dashboard",
                    "integration": "tunnel_system"
                }
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/register",
                json=registration_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Ферма зарегистрирована в Tunnel Broker: {result}")
                self.is_registered = True
                return True
            else:
                logger.error(f"❌ Ошибка регистрации: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Tunnel Broker: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Отправка heartbeat в Tunnel Broker"""
        try:
            current_data = self.get_current_data()
            heartbeat_data = {
                "farm_id": self.farm_id,
                "status": "online",
                "metadata": {
                    "last_data_update": current_data.get("timestamp", time.time()),
                    "devices_count": current_data.get("devices_count", 0),
                    "devices_with_issues": current_data.get("devices_with_issues", 0),
                    "farm_status": current_data.get("farm_status", "online")
                }
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/heartbeat",
                json=heartbeat_data,
                timeout=10
            )
            
            if response.status_code == 200:
                self.last_heartbeat = time.time()
                logger.debug("💓 Heartbeat отправлен успешно")
                return True
            else:
                logger.warning(f"⚠️ Ошибка heartbeat: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка отправки heartbeat: {e}")
            return False
    
    async def heartbeat_loop(self, interval: int = 300):
        """Цикл отправки heartbeat"""
        logger.info(f"💓 Запуск heartbeat цикла каждые {interval} секунд")
        
        while True:
            try:
                if self.is_registered:
                    await self.send_heartbeat()
                else:
                    logger.warning("⚠️ Ферма не зарегистрирована, попытка регистрации...")
                    await self.register_with_broker()
                
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"❌ Ошибка в heartbeat цикле: {e}")
                await asyncio.sleep(60)
    
    def get_local_ip(self) -> str:
        """Получение локального IP адреса"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "127.0.0.1"
    
    def run_api_server(self, host: str = "0.0.0.0", port: int = None):
        """Запуск API сервера в отдельном потоке"""
        if port is None:
            port = self.local_port
        
        app = self.setup_tunnel_api_proxy()
        
        def start_server():
            logger.info(f"🚀 Запуск EDGE Tunnel API сервера на {host}:{port}")
            logger.info("   📊 Доступные endpoints:")
            logger.info("   • GET /health - проверка состояния")
            logger.info("   • GET /api/data/current - текущие данные")
            logger.info("   • GET /api/data/statistics - статистика фермы")
            logger.info("   • GET /api/device/<id> - данные устройства")
            logger.info("   • GET /api/edge/* - прокси к EDGE API")
            
            app.run(host=host, port=port, debug=False, threaded=True)
        
        server_thread = threading.Thread(target=start_server, daemon=False)
        server_thread.start()
        return server_thread
    
    async def start(self, api_host: str = "0.0.0.0", api_port: int = None):
        """Запуск EDGE Tunnel Client"""
        logger.info(f"🚀 Запуск EDGE Tunnel Client для фермы {self.farm_name}")
        
        if not TUNNEL_SYSTEM_AVAILABLE:
            logger.error("❌ Tunnel System недоступна")
            return False
        
        try:
            # 1. Запуск API сервера
            logger.info("1️⃣ Запуск API сервера...")
            self.run_api_server(host=api_host, port=api_port or self.local_port)
            
            # Даем серверу время на запуск
            await asyncio.sleep(2)
            
            # 2. Регистрация в Tunnel Broker
            logger.info("2️⃣ Регистрация в Tunnel Broker...")
            registration_attempts = 3
            for attempt in range(registration_attempts):
                if await self.register_with_broker():
                    break
                else:
                    if attempt < registration_attempts - 1:
                        logger.warning(f"⚠️ Попытка регистрации {attempt + 1} неудачна, повтор через 10 секунд...")
                        await asyncio.sleep(10)
                    else:
                        logger.error("❌ Все попытки регистрации исчерпаны")
                        raise Exception("Не удалось зарегистрироваться в Tunnel Broker")
            
            # 3. Запуск heartbeat цикла
            logger.info("3️⃣ Запуск heartbeat цикла...")
            await self.heartbeat_loop()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска: {e}")
            raise


# Глобальный экземпляр
_tunnel_client: Optional[EDGETunnelClient] = None


def get_tunnel_client(broker_url: str = None,
                     farm_id: str = None,
                     owner_id: str = None,
                     farm_name: str = None,
                     local_port: int = 8080) -> Optional[EDGETunnelClient]:
    """Получение глобального экземпляра Tunnel Client"""
    global _tunnel_client
    
    if _tunnel_client is None and all([broker_url, farm_id, owner_id, farm_name]):
        _tunnel_client = EDGETunnelClient(
            broker_url=broker_url,
            farm_id=farm_id,
            owner_id=owner_id,
            farm_name=farm_name,
            local_port=local_port
        )
    
    return _tunnel_client


def is_tunnel_system_available() -> bool:
    """Проверка доступности Tunnel System"""
    return TUNNEL_SYSTEM_AVAILABLE


async def start_edge_tunnel_client(broker_url: str,
                                  farm_id: str,
                                  owner_id: str,
                                  farm_name: str,
                                  local_port: int = 8080,
                                  api_host: str = "0.0.0.0"):
    """Convenience функция для запуска EDGE Tunnel Client"""
    client = get_tunnel_client(
        broker_url=broker_url,
        farm_id=farm_id,
        owner_id=owner_id,
        farm_name=farm_name,
        local_port=local_port
    )
    
    if client:
        await client.start(api_host=api_host, api_port=local_port)
    else:
        logger.error("❌ Не удалось создать Tunnel Client")


if __name__ == "__main__":
    # Тестовый запуск
    logging.basicConfig(level=logging.INFO)
    
    if is_tunnel_system_available():
        print("✅ Tunnel System доступна")
        
        # Тест клиента
        client = EDGETunnelClient(
            broker_url="http://localhost:8080",
            farm_id=f"edge-{socket.gethostname()}",
            owner_id="user_123456",
            farm_name="EDGE Test Farm",
            local_port=8081
        )
        
        # Тест получения данных
        data = client.get_current_data()
        print(f"📊 Данные фермы: {data}")
        
        # Тест capabilities
        capabilities = client.get_farm_capabilities()
        print(f"🔧 Capabilities: {capabilities}")
    else:
        print("❌ Tunnel System недоступна")