#!/usr/bin/env python3
"""
TailscaleManager - интеграция с Tailscale API для управления mesh-сетью
Ported from EDGE to APP for mobile application Tailscale integration
"""

import asyncio
import json
import logging
import socket
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

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

    async def get_farm_devices(self) -> list[TailscaleFarm]:
        """Поиск ферм в tailnet по тегам или именам (alias for find_farms)"""
        return await self.find_farms()

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

                if is_farm:
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
                        status="online" if device.online else "offline",
                    )
                    farms.append(farm)

            logger.info(f"🚜 Найдено {len(farms)} ферм в Tailnet")
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

    async def ping_device(self, ip: str, port: int = 80) -> bool:
        """Проверка доступности устройства по IP и порту"""
        try:
            conn = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=5)
            
            async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
                try:
                    url = f"http://{ip}:{port}/"
                    async with session.get(url) as response:
                        # Любой HTTP ответ означает что сервис доступен
                        return True
                except aiohttp.ClientConnectionError:
                    # Проверяем TCP подключение
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(ip, port), timeout=5
                        )
                        writer.close()
                        await writer.wait_closed()
                        return True
                    except:
                        return False
                except:
                    return False

        except Exception as e:
            logger.debug(f"Ping {ip}:{port} failed: {e}")
            return False

    def is_tailscale_connected(self) -> bool:
        """Проверка, подключен ли Tailscale"""
        return self.is_tailscale_running()

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

    async def create_auth_key(self, ephemeral: bool = False, reusable: bool = True, tags: list[str] = None) -> str:
        """Создание auth key для новых устройств"""
        try:
            if not self.session:
                async with self:
                    return await self.create_auth_key(ephemeral, reusable, tags)

            if tags is None:
                tags = ["tag:farm"]

            payload = {
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

            url = f"{self.base_url}/tailnet/{self.tailnet}/keys"
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Tailscale API error: {response.status} - {error_text}")

                data = await response.json()
                auth_key = data.get("key", "")
                
                logger.info(f"✅ Создан auth key для {tags}")
                return auth_key

        except Exception as e:
            logger.error(f"❌ Ошибка создания auth key: {e}")
            raise


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )
    logger.info("TailscaleManager for APP - ready for integration")