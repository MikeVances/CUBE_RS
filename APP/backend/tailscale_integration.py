#!/usr/bin/env python3
"""
Tailscale Integration для Web Application
Интеграция с Tailscale Manager для управления mesh-сетью из веб-интерфейса
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

# Импорт из локального модуля
from tailscale_manager import TailscaleManager

logger = logging.getLogger(__name__)


class WebTailscaleService:
    """Сервис интеграции Tailscale для веб-приложения"""

    def __init__(self, tailnet: str, api_key: str):
        self.tailnet = tailnet
        self.api_key = api_key
        self._manager: Optional[TailscaleManager] = None
        self._devices_cache = []
        self._farms_cache = []
        self._cache_timestamp = None
        self.cache_ttl = 60  # 60 секунд TTL для кэша

    async def get_manager(self) -> TailscaleManager:
        """Получение менеджера с async context"""
        if not self._manager:
            self._manager = TailscaleManager(self.tailnet, self.api_key)
            await self._manager.__aenter__()
        return self._manager

    async def close(self):
        """Закрытие соединений"""
        if self._manager:
            await self._manager.__aexit__(None, None, None)
            self._manager = None

    def _is_cache_valid(self) -> bool:
        """Проверка актуальности кэша"""
        if not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp).seconds < self.cache_ttl

    async def get_tailnet_status(self) -> dict[str, Any]:
        """Получение общего статуса tailnet"""
        try:
            manager = await self.get_manager()

            # Получаем актуальные данные
            devices = await manager.get_devices()
            farms = await manager.get_farm_devices()

            # Подсчет статистики
            online_devices = sum(1 for d in devices if d.online)
            total_devices = len(devices)
            online_farms = sum(1 for f in farms if f.device.online)
            total_farms = len(farms)

            # Проверка локального подключения
            local_ip = manager.get_local_tailscale_ip()
            is_connected = manager.is_tailscale_connected()

            return {
                "status": "success",
                "tailnet": self.tailnet,
                "devices": {
                    "total": total_devices,
                    "online": online_devices,
                    "offline": total_devices - online_devices,
                },
                "farms": {
                    "total": total_farms,
                    "online": online_farms,
                    "offline": total_farms - online_farms,
                },
                "local": {
                    "connected": is_connected,
                    "ip": local_ip,
                    "hostname": manager._manager.hostname
                    if hasattr(manager, "_manager")
                    else "unknown",
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Ошибка получения статуса tailnet: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def get_devices_list(
        self, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """Получение списка всех устройств в tailnet"""
        try:
            if not force_refresh and self._is_cache_valid():
                return [asdict(device) for device in self._devices_cache]

            manager = await self.get_manager()
            devices = await manager.get_devices()

            # Обновляем кэш
            self._devices_cache = devices
            self._cache_timestamp = datetime.now()

            # Дополняем данные проверкой доступности для онлайн устройств
            devices_data = []
            for device in devices:
                device_dict = asdict(device)

                # Проверяем доступность API если устройство онлайн
                if device.online:
                    is_reachable = await manager.ping_device(device.tailscale_ip)
                    device_dict["api_reachable"] = is_reachable
                else:
                    device_dict["api_reachable"] = False

                devices_data.append(device_dict)

            logger.info(f"Получено {len(devices_data)} устройств")
            return devices_data

        except Exception as e:
            logger.error(f"Ошибка получения устройств: {e}")
            return []

    async def get_farms_list(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Получение списка ферм (устройств с тегом farm)"""
        try:
            if not force_refresh and self._is_cache_valid() and self._farms_cache:
                return [asdict(farm) for farm in self._farms_cache]

            manager = await self.get_manager()
            farms = await manager.get_farm_devices()

            # Обновляем кэш
            self._farms_cache = farms

            # Проверяем доступность API для каждой фермы
            farms_data = []
            for farm in farms:
                farm_dict = asdict(farm)

                if farm.device.online:
                    # Проверяем доступность API
                    is_reachable = await manager.ping_device(
                        farm.device.tailscale_ip, farm.api_port
                    )
                    farm_dict["api_reachable"] = is_reachable

                    # Можно добавить проверку специфичных endpoints фермы
                    if is_reachable:
                        farm_dict["status"] = "online"
                    else:
                        farm_dict["status"] = "connected_but_api_down"
                else:
                    farm_dict["api_reachable"] = False
                    farm_dict["status"] = "offline"

                farms_data.append(farm_dict)

            logger.info(f"Получено {len(farms_data)} ферм")
            return farms_data

        except Exception as e:
            logger.error(f"Ошибка получения ферм: {e}")
            return []

    async def create_farm_auth_key(
        self, ephemeral: bool = False, reusable: bool = True
    ) -> dict[str, Any]:
        """Создание ключа авторизации для новой фермы"""
        try:
            manager = await self.get_manager()

            auth_key = await manager.create_auth_key(
                ephemeral=ephemeral, reusable=reusable, tags=["tag:farm"]
            )

            return {
                "status": "success",
                "auth_key": auth_key,
                "ephemeral": ephemeral,
                "reusable": reusable,
                "tags": ["tag:farm"],
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Ошибка создания auth key: {e}")
            return {"status": "error", "message": str(e)}

    async def get_device_details(self, device_id: str) -> dict[str, Any]:
        """Получение детальной информации об устройстве"""
        try:
            devices = await self.get_devices_list()
            device = next((d for d in devices if d["id"] == device_id), None)

            if not device:
                return {"status": "error", "message": "Устройство не найдено"}

            # Дополнительные проверки для детального просмотра
            if device["online"]:
                manager = await self.get_manager()

                # Проверяем доступность различных портов
                device["port_checks"] = {
                    "22": await manager.ping_device(device["tailscale_ip"], 22),  # SSH
                    "80": await manager.ping_device(device["tailscale_ip"], 80),  # HTTP
                    "8080": await manager.ping_device(
                        device["tailscale_ip"], 8080
                    ),  # API
                    "5000": await manager.ping_device(
                        device["tailscale_ip"], 5000
                    ),  # Flask dev
                }

            return {
                "status": "success",
                "device": device,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Ошибка получения деталей устройства {device_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def check_farm_connectivity(
        self, tailscale_ip: str, api_port: int = 8080
    ) -> dict[str, Any]:
        """Проверка подключения к ферме и её API"""
        try:
            manager = await self.get_manager()

            # Проверяем базовое подключение
            basic_ping = await manager.ping_device(tailscale_ip, api_port)

            result = {
                "status": "success",
                "tailscale_ip": tailscale_ip,
                "api_port": api_port,
                "basic_connectivity": basic_ping,
                "timestamp": datetime.now().isoformat(),
            }

            if basic_ping:
                # Можно добавить дополнительные проверки:
                # - HTTP запрос к API фермы
                # - Проверка версии API
                # - Проверка доступности данных КУБ-1063
                result["detailed_checks"] = {
                    "api_available": True,  # Заглушка для будущих проверок
                    "version_check": "pending",
                    "data_access": "pending",
                }
            else:
                result["detailed_checks"] = {"api_available": False}

            return result

        except Exception as e:
            logger.error(f"Ошибка проверки подключения к {tailscale_ip}: {e}")
            return {"status": "error", "message": str(e), "tailscale_ip": tailscale_ip}


class TailscaleWebConfig:
    """Конфигурация Tailscale для веб-приложения"""

    def __init__(self):
        # Получаем конфигурацию из переменных окружения
        self.tailnet = os.environ.get("TAILSCALE_TAILNET", "")
        self.api_key = os.environ.get("TAILSCALE_API_KEY", "")
        self.enabled = os.environ.get("TAILSCALE_ENABLED", "false").lower() == "true"

    def is_configured(self) -> bool:
        """Проверка корректности конфигурации"""
        return bool(self.enabled and self.tailnet and self.api_key)

    def get_config_status(self) -> dict[str, Any]:
        """Получение статуса конфигурации"""
        return {
            "enabled": self.enabled,
            "tailnet_configured": bool(self.tailnet),
            "api_key_configured": bool(self.api_key),
            "fully_configured": self.is_configured(),
            "tailnet": self.tailnet if self.tailnet else "не настроен",
        }


# Глобальный экземпляр для использования в Flask routes
_tailscale_service: Optional[WebTailscaleService] = None
_tailscale_config = TailscaleWebConfig()


def get_tailscale_service() -> Optional[WebTailscaleService]:
    """Получение глобального экземпляра Tailscale сервиса"""
    global _tailscale_service

    if not _tailscale_config.is_configured():
        return None

    if not _tailscale_service:
        _tailscale_service = WebTailscaleService(
            _tailscale_config.tailnet, _tailscale_config.api_key
        )

    return _tailscale_service


def get_tailscale_config() -> TailscaleWebConfig:
    """Получение конфигурации Tailscale"""
    return _tailscale_config


async def cleanup_tailscale_service():
    """Очистка ресурсов Tailscale сервиса"""
    global _tailscale_service
    if _tailscale_service:
        await _tailscale_service.close()
        _tailscale_service = None


# Пример использования для тестирования
async def main():
    """Тест интеграции"""
    config = get_tailscale_config()

    print("=== Конфигурация Tailscale ===")
    print(json.dumps(config.get_config_status(), indent=2, ensure_ascii=False))

    if not config.is_configured():
        print("\n⚠️ Tailscale не настроен!")
        print("Установите переменные окружения:")
        print("  TAILSCALE_ENABLED=true")
        print("  TAILSCALE_TAILNET=your-tailnet.ts.net")
        print("  TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx")
        return

    service = get_tailscale_service()
    if not service:
        print("❌ Не удалось создать Tailscale сервис")
        return

    try:
        print("\n=== Статус Tailnet ===")
        status = await service.get_tailnet_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

        print("\n=== Список устройств ===")
        devices = await service.get_devices_list()
        for device in devices:
            status_icon = "🟢" if device["online"] else "🔴"
            api_icon = "✅" if device.get("api_reachable") else "❌"
            print(
                f"{status_icon} {device['hostname']} ({device['tailscale_ip']}) API: {api_icon}"
            )

        print("\n=== Список ферм ===")
        farms = await service.get_farms_list()
        for farm in farms:
            status_icon = "🟢" if farm["device"]["online"] else "🔴"
            api_icon = "✅" if farm.get("api_reachable") else "❌"
            print(
                f"🏭 {status_icon} {farm['farm_name']} ({farm['device']['tailscale_ip']}) API: {api_icon}"
            )

    except Exception as e:
        print(f"❌ Ошибка: {e}")

    finally:
        await cleanup_tailscale_service()


if __name__ == "__main__":
    asyncio.run(main())
