#!/usr/bin/env python3
"""
Tailscale Integration для Web Application
Интеграция с Tailscale Manager для управления mesh-сетью из веб-интерфейса
Ported from archive to SERVER for web-based Tailscale management
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional, Dict, List

logger = logging.getLogger(__name__)


class TailscaleWebIntegration:
    """Веб-интеграция с Tailscale для централизованного управления mesh-сетью"""

    def __init__(self):
        self.tailnet = ""
        self.api_key = ""
        self._devices_cache = []
        self._network_cache = {}
        self._cache_timestamp = None
        self.cache_ttl = 60  # 60 секунд TTL для кэша
        self._manager = None
        
        logger.info("🔗 Tailscale Web Integration инициализирован")

    def configure(self, tailnet: str, api_key: str):
        """Конфигурация подключения к Tailscale"""
        self.tailnet = tailnet
        self.api_key = api_key
        logger.info(f"🔗 Tailscale настроен для {tailnet}")

    def _is_cache_valid(self) -> bool:
        """Проверка актуальности кэша"""
        if not self._cache_timestamp:
            return False
        return (time.time() - self._cache_timestamp) < self.cache_ttl

    async def _get_manager(self):
        """Получение Tailscale менеджера с импортом из EDGE"""
        if not self._manager and self.tailnet and self.api_key:
            try:
                # Пытаемся импортировать из EDGE tunnel_system
                from ..tunnel_system.tailscale_manager import TailscaleManager
                self._manager = TailscaleManager(self.tailnet, self.api_key)
                logger.debug("✅ TailscaleManager подключен из EDGE")
            except ImportError:
                # Если не доступен, создаем заглушку
                logger.warning("⚠️ TailscaleManager недоступен, используем заглушку")
                self._manager = None
        
        return self._manager

    async def get_network_overview(self) -> Dict[str, Any]:
        """Получение общего обзора Tailscale сети"""
        try:
            if self._is_cache_valid() and self._network_cache:
                logger.debug("📋 Используем кэш для network overview")
                return self._network_cache

            manager = await self._get_manager()
            if not manager:
                return self._get_fallback_network_overview()

            # Получаем устройства через менеджер
            devices = await manager.get_devices()
            farms = await manager.find_farms()

            # Подсчет статистики
            online_devices = sum(1 for d in devices if d.online)
            total_devices = len(devices)
            online_farms = sum(1 for f in farms if f.device.online)
            total_farms = len(farms)

            # Проверка локального подключения
            local_ip = manager.get_local_tailscale_ip()
            is_connected = bool(local_ip)

            network_overview = {
                "status": "success",
                "tailnet": self.tailnet,
                "local_connection": {
                    "connected": is_connected,
                    "ip": local_ip,
                    "status": "online" if is_connected else "disconnected"
                },
                "devices": {
                    "total": total_devices,
                    "online": online_devices,
                    "offline": total_devices - online_devices,
                    "farms": online_farms,
                    "other": online_devices - online_farms
                },
                "farms": {
                    "total": total_farms,
                    "online": online_farms,
                    "offline": total_farms - online_farms
                },
                "last_updated": datetime.now().isoformat()
            }

            # Обновляем кэш
            self._network_cache = network_overview
            self._cache_timestamp = time.time()

            return network_overview

        except Exception as e:
            logger.error(f"❌ Ошибка получения обзора Tailscale сети: {e}")
            return self._get_fallback_network_overview(error=str(e))

    def _get_fallback_network_overview(self, error: str = None) -> Dict[str, Any]:
        """Заглушка для network overview в случае недоступности Tailscale"""
        return {
            "status": "error" if error else "disabled",
            "tailnet": self.tailnet or "not_configured",
            "local_connection": {
                "connected": False,
                "ip": "",
                "status": "unavailable"
            },
            "devices": {
                "total": 0,
                "online": 0,
                "offline": 0,
                "farms": 0,
                "other": 0
            },
            "farms": {
                "total": 0,
                "online": 0,
                "offline": 0
            },
            "error": error,
            "message": "Tailscale integration not available" if not error else f"Tailscale error: {error}",
            "last_updated": datetime.now().isoformat()
        }

    async def get_devices_list(self) -> List[Dict[str, Any]]:
        """Получение списка устройств в Tailscale сети"""
        try:
            if self._is_cache_valid() and self._devices_cache:
                logger.debug("📋 Используем кэш для devices list")
                return self._devices_cache

            manager = await self._get_manager()
            if not manager:
                return []

            devices = await manager.get_devices()
            devices_list = []

            for device in devices:
                device_info = {
                    "id": device.id,
                    "hostname": device.hostname,
                    "name": device.name,
                    "tailscale_ip": device.tailscale_ip,
                    "os": device.os,
                    "online": device.online,
                    "last_seen": device.last_seen,
                    "tags": device.tags,
                    "device_type": "unknown",
                    "capabilities": []
                }

                # Определяем тип устройства по тегам или имени
                if "farm" in device.tags or any(kw in device.hostname.lower() 
                                              for kw in ["farm", "kub", "greenhouse"]):
                    device_info["device_type"] = "farm"
                    device_info["capabilities"] = ["kub1063", "monitoring"]
                elif "mobile" in device.tags or "app" in device.hostname.lower():
                    device_info["device_type"] = "mobile"
                    device_info["capabilities"] = ["tunnel_access"]
                elif "server" in device.tags or "server" in device.hostname.lower():
                    device_info["device_type"] = "server"
                    device_info["capabilities"] = ["management", "api"]
                else:
                    device_info["device_type"] = "client"
                    device_info["capabilities"] = ["basic_access"]

                devices_list.append(device_info)

            # Обновляем кэш
            self._devices_cache = devices_list
            self._cache_timestamp = time.time()

            logger.info(f"🔗 Найдено {len(devices_list)} устройств в Tailscale сети")
            return devices_list

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка устройств Tailscale: {e}")
            return []

    async def get_network_status(self) -> Dict[str, Any]:
        """Получение подробного статуса Tailscale сети"""
        try:
            manager = await self._get_manager()
            if not manager:
                return {
                    "status": "disabled",
                    "message": "Tailscale manager not available"
                }

            # Проверяем локальное подключение
            local_ip = manager.get_local_tailscale_ip()
            is_running = manager.is_tailscale_running()
            is_connected = await manager.ensure_tailscale_connection()

            # Получаем информацию об устройствах
            devices = await manager.get_devices()
            farms = await manager.find_farms()

            # Тестируем соединения с фермами
            farm_connections = []
            for farm in farms[:5]:  # Тестируем только первые 5 ферм
                connection_test = await manager.test_farm_connection(farm)
                farm_connections.append({
                    "farm_name": farm.farm_name,
                    "tailscale_ip": farm.device.tailscale_ip,
                    "connection_status": connection_test.get("status", "unknown"),
                    "response_time": connection_test.get("response_time", "N/A")
                })

            return {
                "status": "success",
                "local_status": {
                    "tailscale_running": is_running,
                    "connected": is_connected,
                    "local_ip": local_ip
                },
                "network_info": {
                    "tailnet": self.tailnet,
                    "total_devices": len(devices),
                    "online_devices": sum(1 for d in devices if d.online),
                    "total_farms": len(farms),
                    "online_farms": sum(1 for f in farms if f.device.online)
                },
                "farm_connections": farm_connections,
                "last_check": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса Tailscale: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to get Tailscale network status"
            }

    async def get_farm_data(self, farm_id: str) -> Dict[str, Any]:
        """Получение данных с конкретной фермы через Tailscale"""
        try:
            manager = await self._get_manager()
            if not manager:
                return {"error": "Tailscale manager not available"}

            farms = await manager.find_farms()
            target_farm = None

            for farm in farms:
                if (farm.device.id == farm_id or 
                    farm.device.hostname == farm_id or 
                    farm.farm_name == farm_id):
                    target_farm = farm
                    break

            if not target_farm:
                return {"error": f"Farm {farm_id} not found"}

            if not target_farm.device.online:
                return {"error": f"Farm {farm_id} is offline"}

            # Получаем данные с фермы
            farm_data = await manager.get_farm_data(target_farm, "api/data/current")
            
            if "error" in farm_data:
                logger.warning(f"⚠️ Ошибка получения данных с фермы {farm_id}: {farm_data['error']}")
            else:
                logger.info(f"📊 Данные получены с фермы {farm_id}")

            return farm_data

        except Exception as e:
            logger.error(f"❌ Ошибка получения данных фермы {farm_id}: {e}")
            return {"error": str(e)}

    async def send_farm_command(self, farm_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """Отправка команды на ферму через Tailscale"""
        try:
            manager = await self._get_manager()
            if not manager:
                return {"error": "Tailscale manager not available"}

            farms = await manager.find_farms()
            target_farm = None

            for farm in farms:
                if (farm.device.id == farm_id or 
                    farm.device.hostname == farm_id or 
                    farm.farm_name == farm_id):
                    target_farm = farm
                    break

            if not target_farm:
                return {"error": f"Farm {farm_id} not found"}

            if not target_farm.device.online:
                return {"error": f"Farm {farm_id} is offline"}

            # Отправляем команду
            result = await manager.send_command_to_farm(target_farm, command)
            
            if "error" in result:
                logger.warning(f"⚠️ Ошибка отправки команды на ферму {farm_id}: {result['error']}")
            else:
                logger.info(f"✅ Команда отправлена на ферму {farm_id}: {command.get('command', 'unknown')}")

            return result

        except Exception as e:
            logger.error(f"❌ Ошибка отправки команды на ферму {farm_id}: {e}")
            return {"error": str(e)}

    def get_tailscale_config(self) -> Dict[str, Any]:
        """Получение текущей конфигурации Tailscale"""
        return {
            "tailnet": self.tailnet,
            "configured": bool(self.tailnet and self.api_key),
            "cache_ttl": self.cache_ttl,
            "last_cache_update": self._cache_timestamp,
            "cache_valid": self._is_cache_valid()
        }

    def clear_cache(self):
        """Очистка кэша Tailscale данных"""
        self._devices_cache.clear()
        self._network_cache.clear()
        self._cache_timestamp = None
        logger.info("🗑️ Кэш Tailscale данных очищен")

    async def refresh_data(self):
        """Принудительное обновление данных Tailscale"""
        self.clear_cache()
        
        # Обновляем основные данные
        await self.get_network_overview()
        await self.get_devices_list()
        
        logger.info("🔄 Данные Tailscale обновлены")

    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики использования Tailscale интеграции"""
        return {
            "configured": bool(self.tailnet and self.api_key),
            "cache_entries": len(self._devices_cache),
            "cache_valid": self._is_cache_valid(),
            "last_update": self._cache_timestamp,
            "tailnet": self.tailnet,
            "cache_ttl_seconds": self.cache_ttl
        }

    async def cleanup(self):
        """Очистка ресурсов"""
        if self._manager:
            try:
                await self._manager.__aexit__(None, None, None)
            except:
                pass
            self._manager = None
        
        self.clear_cache()
        logger.info("🧹 Tailscale Web Integration очищен")


# Глобальный экземпляр для использования в веб-приложении
_tailscale_integration = None


def get_tailscale_integration() -> TailscaleWebIntegration:
    """Получение глобального экземпляра Tailscale интеграции (Singleton)"""
    global _tailscale_integration
    if _tailscale_integration is None:
        _tailscale_integration = TailscaleWebIntegration()
    return _tailscale_integration


# Утилитарные функции для совместимости с архивной версией
async def get_tailscale_service() -> TailscaleWebIntegration:
    """Совместимость: получение сервиса Tailscale"""
    return get_tailscale_integration()


def get_tailscale_config() -> Dict[str, Any]:
    """Совместимость: получение конфигурации Tailscale"""
    integration = get_tailscale_integration()
    return integration.get_tailscale_config()


async def cleanup_tailscale_service():
    """Совместимость: очистка сервиса Tailscale"""
    global _tailscale_integration
    if _tailscale_integration:
        await _tailscale_integration.cleanup()
        _tailscale_integration = None


if __name__ == "__main__":
    # Пример использования Tailscale Web Integration
    import asyncio
    
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )
    
    async def test_tailscale_integration():
        """Тестирование Tailscale интеграции"""
        integration = TailscaleWebIntegration()
        
        # Настройка (в реальности берется из переменных окружения)
        integration.configure(
            tailnet="test-tailnet.ts.net",
            api_key="tskey-api-test"
        )
        
        print("🔗 Tailscale Web Integration настроен")
        
        # Получение обзора сети
        network_overview = await integration.get_network_overview()
        print(f"🌐 Network Overview: {json.dumps(network_overview, indent=2)}")
        
        # Получение списка устройств
        devices = await integration.get_devices_list()
        print(f"📱 Devices: {len(devices)} found")
        
        # Статистика
        stats = integration.get_statistics()
        print(f"📊 Statistics: {json.dumps(stats, indent=2)}")
        
        # Очистка
        await integration.cleanup()
        print("✅ Cleanup completed")
    
    # Запуск теста
    asyncio.run(test_tailscale_integration())