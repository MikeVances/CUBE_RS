#!/usr/bin/env python3
"""
TailscaleManager - интеграция с Tailscale API для управления mesh-сетью
"""

import asyncio
import json
import logging
import subprocess
import socket
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TailscaleDevice:
    """Информация об устройстве в tailnet"""
    id: str
    hostname: str
    name: str
    tailscale_ip: str
    os: str
    online: bool
    last_seen: str
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

@dataclass  
class TailscaleFarm:
    """Информация о ферме в tailnet"""
    device: TailscaleDevice
    farm_name: str = ""
    capabilities: List[str] = None
    api_port: int = 8080
    status: str = "unknown"
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = ["kub1063", "monitoring"]
        if self.metadata is None:
            self.metadata = {}
        if not self.farm_name:
            self.farm_name = self.device.hostname

class TailscaleManager:
    """Менеджер для работы с Tailscale API и локальным агентом"""
    
    def __init__(self, tailnet: str, api_key: str):
        self.tailnet = tailnet
        self.api_key = api_key
        self.base_url = "https://api.tailscale.com/api/v2"
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Выполнение запроса к Tailscale API"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            if method.upper() == "GET":
                async with self.session.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method.upper() == "POST":
                async with self.session.post(url, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method.upper() == "DELETE":
                async with self.session.delete(url) as response:
                    response.raise_for_status()
                    return {}
                    
        except aiohttp.ClientError as e:
            logger.error(f"Tailscale API error: {e}")
            raise
    
    async def get_devices(self, tag_filter: str = None) -> List[TailscaleDevice]:
        """Получение списка устройств в tailnet"""
        try:
            response = await self._make_request("GET", f"tailnet/{self.tailnet}/devices")
            devices = []
            
            for device_data in response.get('devices', []):
                # Извлекаем Tailscale IP (обычно первый в списке addresses)
                addresses = device_data.get('addresses', [])
                tailscale_ip = addresses[0] if addresses else "unknown"
                
                device = TailscaleDevice(
                    id=device_data['nodeId'],
                    hostname=device_data['hostname'],
                    name=device_data['name'],
                    tailscale_ip=tailscale_ip,
                    os=device_data['os'],
                    online=device_data['online'],
                    last_seen=device_data['lastSeen'],
                    tags=device_data.get('tags', [])
                )
                
                # Фильтрация по тегу если указан
                if tag_filter:
                    if f"tag:{tag_filter}" in device.tags:
                        devices.append(device)
                else:
                    devices.append(device)
                    
            logger.info(f"Найдено {len(devices)} устройств в tailnet")
            return devices
            
        except Exception as e:
            logger.error(f"Ошибка получения устройств: {e}")
            return []
    
    async def get_farm_devices(self) -> List[TailscaleFarm]:
        """Получение устройств с тегом 'farm'"""
        devices = await self.get_devices(tag_filter="farm")
        farms = []
        
        for device in devices:
            farm = TailscaleFarm(device=device)
            farms.append(farm)
            
        logger.info(f"Найдено {len(farms)} ферм в tailnet")
        return farms
    
    async def create_auth_key(self, 
                            ephemeral: bool = False,
                            reusable: bool = True,
                            tags: List[str] = None) -> str:
        """Создание ключа авторизации для новых устройств"""
        if tags is None:
            tags = ["tag:farm"]
            
        data = {
            "capabilities": {
                "devices": {
                    "create": {
                        "reusable": reusable,
                        "ephemeral": ephemeral,
                        "tags": tags
                    }
                }
            }
        }
        
        try:
            response = await self._make_request("POST", f"tailnet/{self.tailnet}/keys", data)
            auth_key = response.get('key')
            logger.info(f"Создан auth key: {auth_key[:20]}...")
            return auth_key
            
        except Exception as e:
            logger.error(f"Ошибка создания auth key: {e}")
            raise
    
    def get_local_tailscale_ip(self) -> Optional[str]:
        """Получение локального Tailscale IP адреса"""
        try:
            # Попытка получить IP через tailscale ip команду
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                ip = result.stdout.strip()
                logger.info(f"Локальный Tailscale IP: {ip}")
                return ip
            else:
                logger.warning(f"Tailscale не установлен или не подключен: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout при получении Tailscale IP")
            return None
        except FileNotFoundError:
            logger.error("Tailscale CLI не найден")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения локального IP: {e}")
            return None
    
    def is_tailscale_connected(self) -> bool:
        """Проверка подключения к Tailscale"""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                status_data = json.loads(result.stdout)
                backend_state = status_data.get('BackendState', '')
                return backend_state == 'Running'
            else:
                return False
                
        except Exception as e:
            logger.error(f"Ошибка проверки статуса Tailscale: {e}")
            return False
    
    async def wait_for_device_online(self, hostname: str, timeout: int = 300) -> bool:
        """Ожидание появления устройства в сети"""
        logger.info(f"Ожидание подключения устройства {hostname}...")
        
        for attempt in range(timeout // 10):
            devices = await self.get_devices()
            for device in devices:
                if device.hostname == hostname and device.online:
                    logger.info(f"Устройство {hostname} подключено: {device.tailscale_ip}")
                    return True
            
            await asyncio.sleep(10)
        
        logger.warning(f"Устройство {hostname} не подключилось за {timeout} секунд")
        return False
    
    async def ping_device(self, tailscale_ip: str, port: int = 8080) -> bool:
        """Проверка доступности устройства"""
        try:
            # Простая проверка TCP подключения
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(tailscale_ip, port),
                timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
            logger.debug(f"Устройство {tailscale_ip}:{port} доступно")
            return True
            
        except asyncio.TimeoutError:
            logger.debug(f"Timeout подключения к {tailscale_ip}:{port}")
            return False
        except Exception as e:
            logger.debug(f"Ошибка подключения к {tailscale_ip}:{port}: {e}")
            return False

class TailscaleFarmRegistrator:
    """Сервис регистрации фермы в Tailscale mesh-сети"""
    
    def __init__(self, tailscale_manager: TailscaleManager, farm_metadata: Dict[str, Any]):
        self.tailscale = tailscale_manager
        self.metadata = farm_metadata
        self.hostname = socket.gethostname()
        
    async def register_farm(self) -> bool:
        """Регистрация фермы в системе"""
        try:
            # 1. Проверяем подключение к Tailscale
            if not self.tailscale.is_tailscale_connected():
                logger.error("Tailscale не подключен")
                return False
            
            # 2. Получаем локальный IP
            local_ip = self.tailscale.get_local_tailscale_ip()
            if not local_ip:
                logger.error("Не удалось получить Tailscale IP")
                return False
            
            # 3. Обновляем метаданные
            self.metadata.update({
                'tailscale_ip': local_ip,
                'hostname': self.hostname,
                'status': 'online',
                'registered_at': asyncio.get_event_loop().time()
            })
            
            logger.info(f"Ферма {self.hostname} зарегистрирована: {local_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка регистрации фермы: {e}")
            return False
    
    async def start_heartbeat(self, interval: int = 300):
        """Запуск heartbeat сервиса"""
        logger.info(f"Запуск heartbeat каждые {interval} секунд")
        
        while True:
            try:
                # Обновляем статус фермы
                if self.tailscale.is_tailscale_connected():
                    self.metadata['last_heartbeat'] = asyncio.get_event_loop().time()
                    self.metadata['status'] = 'online'
                else:
                    self.metadata['status'] = 'disconnected'
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Ошибка heartbeat: {e}")
                await asyncio.sleep(60)  # Retry через минуту

# Пример использования
async def main():
    """Демонстрация использования TailscaleManager"""
    
    # Настройки (в продакшене из конфига)
    TAILNET = "your-tailnet.ts.net"
    API_KEY = "tskey-api-xxxxxxxxxx"
    
    async with TailscaleManager(TAILNET, API_KEY) as ts:
        
        # Получение всех устройств
        print("=== Все устройства в tailnet ===")
        devices = await ts.get_devices()
        for device in devices:
            print(f"🖥️  {device.hostname} ({device.tailscale_ip}) - {'🟢' if device.online else '🔴'}")
        
        # Получение только ферм
        print("\n=== Фермы в tailnet ===")
        farms = await ts.get_farm_devices()
        for farm in farms:
            status = "🟢" if farm.device.online else "🔴"
            print(f"🏭 {farm.farm_name} ({farm.device.tailscale_ip}) {status}")
        
        # Создание auth key для новой фермы
        print("\n=== Создание auth key ===")
        try:
            auth_key = await ts.create_auth_key(tags=["tag:farm"])
            print(f"🔑 Auth key для новой фермы: {auth_key[:20]}...")
        except Exception as e:
            print(f"❌ Ошибка создания ключа: {e}")
        
        # Проверка локального подключения
        print("\n=== Локальный статус ===")
        local_ip = ts.get_local_tailscale_ip()
        connected = ts.is_tailscale_connected()
        print(f"📍 Локальный IP: {local_ip}")
        print(f"🔗 Подключен: {'✅' if connected else '❌'}")

if __name__ == "__main__":
    asyncio.run(main())