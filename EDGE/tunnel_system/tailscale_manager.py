#!/usr/bin/env python3
"""
TailscaleManager - интеграция с Tailscale API для управления mesh-сетью
Ported from archive to EDGE for Tailscale mesh networking integration
"""

import asyncio
import json
import logging
import socket
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

# Import EDGE core components
try:
    from ..core.log_filter import get_secure_logger
    logger = get_secure_logger(__name__)
except ImportError:
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
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class TailscaleFarm:
    """Информация о ферме в tailnet"""

    device: TailscaleDevice
    farm_name: str = ""
    capabilities: list[str] = None
    api_port: int = 8080
    status: str = "unknown"
    metadata: dict[str, Any] = None

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
                "Content-Type": "application/json",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def get_devices(self) -> list[TailscaleDevice]:
        """Получение списка устройств в tailnet"""
        try:
            if not self.session:
                async with self:
                    return await self.get_devices()

            url = f"{self.base_url}/tailnet/{self.tailnet}/devices"
            async with self.session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Tailscale API error: {response.status} - {error_text}")

                data = await response.json()
                devices = []

                for device_data in data.get("devices", []):
                    device = TailscaleDevice(
                        id=device_data["id"],
                        hostname=device_data["hostname"],
                        name=device_data["name"],
                        tailscale_ip=device_data["addresses"][0] if device_data.get("addresses") else "",
                        os=device_data.get("os", "unknown"),
                        online=device_data.get("online", False),
                        last_seen=device_data.get("lastSeen", ""),
                        tags=device_data.get("tags", []),
                    )
                    devices.append(device)

                logger.info(f"🔗 Найдено {len(devices)} устройств в Tailnet {self.tailnet}")
                return devices

        except Exception as e:
            logger.error(f"❌ Ошибка получения устройств Tailscale: {e}")
            return []

    async def find_farms(self) -> list[TailscaleFarm]:
        """Поиск ферм в tailnet по тегам или именам"""
        try:
            devices = await self.get_devices()
            farms = []

            for device in devices:
                # Проверяем тег "farm" или имя содержащее "farm"
                is_farm = (
                    "farm" in device.tags
                    or "kub" in device.hostname.lower()
                    or "greenhouse" in device.hostname.lower()
                    or "farm" in device.hostname.lower()
                )

                if is_farm and device.online:
                    # Пытаемся определить возможности фермы
                    capabilities = ["kub1063"]
                    if "monitoring" in device.tags:
                        capabilities.append("monitoring")
                    if "control" in device.tags:
                        capabilities.append("control")

                    farm = TailscaleFarm(
                        device=device,
                        farm_name=device.hostname,
                        capabilities=capabilities,
                        status="online",
                    )
                    farms.append(farm)

            logger.info(f"🚜 Найдено {len(farms)} активных ферм в Tailnet")
            return farms

        except Exception as e:
            logger.error(f"❌ Ошибка поиска ферм: {e}")
            return []

    def get_local_tailscale_ip(self) -> str:
        """Получение локального IP адреса Tailscale"""
        try:
            # Пытаемся получить IP из `tailscale ip`
            result = subprocess.run(
                ["tailscale", "ip"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                tailscale_ip = result.stdout.strip().split()[0]  # Берем первый IP
                logger.info(f"🔗 Локальный Tailscale IP: {tailscale_ip}")
                return tailscale_ip

            # Альтернативный способ - через `tailscale status`
            result = subprocess.run(
                ["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                status_data = json.loads(result.stdout)
                self_info = status_data.get("Self", {})
                tailscale_ips = self_info.get("TailscaleIPs", [])

                if tailscale_ips:
                    tailscale_ip = tailscale_ips[0]
                    logger.info(f"🔗 Локальный Tailscale IP (из status): {tailscale_ip}")
                    return tailscale_ip

            logger.warning("⚠️ Не удалось получить Tailscale IP")
            return ""

        except subprocess.TimeoutExpired:
            logger.error("❌ Таймаут получения Tailscale IP")
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка получения Tailscale IP: {e}")
            return ""

    async def test_farm_connection(self, farm: TailscaleFarm) -> dict:
        """Тест соединения с фермой"""
        try:
            url = f"http://{farm.device.tailscale_ip}:{farm.api_port}/health"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Соединение с фермой {farm.farm_name} успешно")
                        return {
                            "status": "ok",
                            "response_time": response.headers.get("X-Response-Time", "unknown"),
                            "farm_data": data,
                        }
                    else:
                        logger.warning(f"⚠️ Ферма {farm.farm_name} ответила с кодом {response.status}")
                        return {"status": "error", "code": response.status}

        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Таймаут соединения с фермой {farm.farm_name}")
            return {"status": "timeout"}
        except Exception as e:
            logger.warning(f"⚠️ Ошибка соединения с фермой {farm.farm_name}: {e}")
            return {"status": "error", "message": str(e)}

    async def get_farm_data(self, farm: TailscaleFarm, endpoint: str = "api/data/current") -> dict:
        """Получение данных с фермы"""
        try:
            url = f"http://{farm.device.tailscale_ip}:{farm.api_port}/{endpoint}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"📊 Получены данные с фермы {farm.farm_name}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка получения данных с фермы {farm.farm_name}: {error_text}")
                        return {"error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"❌ Ошибка запроса данных с фермы {farm.farm_name}: {e}")
            return {"error": str(e)}

    async def send_command_to_farm(self, farm: TailscaleFarm, command: dict) -> dict:
        """Отправка команды на ферму"""
        try:
            url = f"http://{farm.device.tailscale_ip}:{farm.api_port}/api/commands"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=command, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Команда отправлена на ферму {farm.farm_name}: {command.get('command')}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка отправки команды на ферму {farm.farm_name}: {error_text}")
                        return {"error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"❌ Ошибка отправки команды на ферму {farm.farm_name}: {e}")
            return {"error": str(e)}

    def is_tailscale_running(self) -> bool:
        """Проверка, запущен ли Tailscale"""
        try:
            result = subprocess.run(
                ["tailscale", "status"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    async def ensure_tailscale_connection(self) -> bool:
        """Убедиться, что Tailscale подключен"""
        try:
            if not self.is_tailscale_running():
                logger.warning("⚠️ Tailscale не запущен")
                return False

            local_ip = self.get_local_tailscale_ip()
            if not local_ip:
                logger.warning("⚠️ Не удалось получить Tailscale IP")
                return False

            logger.info(f"✅ Tailscale подключен: {local_ip}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка проверки Tailscale соединения: {e}")
            return False


class TailscaleFarmRegistrator:
    """Регистратор фермы в Tailscale mesh-сети"""

    def __init__(self, tailscale_manager: TailscaleManager, farm_metadata: dict):
        self.tailscale_manager = tailscale_manager
        self.farm_metadata = farm_metadata
        self.local_hostname = socket.gethostname()

    async def register_farm(self) -> bool:
        """Регистрация фермы в Tailscale"""
        try:
            logger.info(f"🚜 Регистрация фермы {self.local_hostname} в Tailscale...")

            # Проверяем соединение с Tailscale
            if not await self.tailscale_manager.ensure_tailscale_connection():
                logger.error("❌ Не удалось установить соединение с Tailscale")
                return False

            # Получаем локальный IP
            local_ip = self.tailscale_manager.get_local_tailscale_ip()
            if not local_ip:
                logger.error("❌ Не удалось получить локальный Tailscale IP")
                return False

            logger.info(f"✅ Ферма {self.local_hostname} зарегистрирована с IP {local_ip}")

            # Дополнительные метаданные для тегирования
            await self._update_farm_tags()

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка регистрации фермы: {e}")
            return False

    async def _update_farm_tags(self):
        """Обновление тегов фермы для идентификации"""
        try:
            # Получаем информацию о текущем устройстве
            devices = await self.tailscale_manager.get_devices()
            current_device = None

            for device in devices:
                if device.hostname == self.local_hostname:
                    current_device = device
                    break

            if not current_device:
                logger.warning("⚠️ Не удалось найти текущее устройство в Tailnet")
                return

            # Формируем теги для фермы
            farm_tags = ["farm", "kub1063"]
            if self.farm_metadata.get("capabilities"):
                farm_tags.extend(self.farm_metadata["capabilities"])

            logger.info(f"🏷️ Рекомендуемые теги для фермы: {farm_tags}")
            logger.info("   Для применения тегов используйте Tailscale Admin Panel")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления тегов фермы: {e}")


# Пример использования
async def example_usage():
    """Пример использования TailscaleManager"""
    logger.info("🔗 Пример использования TailscaleManager")

    tailnet = "your-tailnet.ts.net"
    api_key = "tskey-api-xxx"

    async with TailscaleManager(tailnet, api_key) as ts_manager:
        # Проверяем соединение
        if not await ts_manager.ensure_tailscale_connection():
            logger.error("❌ Tailscale не подключен")
            return

        # Ищем фермы
        farms = await ts_manager.find_farms()
        logger.info(f"🚜 Найдено ферм: {len(farms)}")

        for farm in farms:
            logger.info(f"   - {farm.farm_name} ({farm.device.tailscale_ip})")

            # Тестируем соединение
            connection_test = await ts_manager.test_farm_connection(farm)
            logger.info(f"     Соединение: {connection_test['status']}")

            if connection_test["status"] == "ok":
                # Получаем данные
                current_data = await ts_manager.get_farm_data(farm)
                if "error" not in current_data:
                    logger.info(f"     Данные получены успешно")
                else:
                    logger.warning(f"     Ошибка получения данных: {current_data['error']}")


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )

    # Запуск примера
    asyncio.run(example_usage())