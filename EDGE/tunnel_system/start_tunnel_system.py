#!/usr/bin/env python3
"""
EDGE Tunnel System Starter - запуск туннельной системы для EDGE устройств
Ported from archive to EDGE for P2P tunnel management
"""

import asyncio
import os
import signal
import sys
import time
from typing import Optional

# Import EDGE components
try:
    from ..core.log_filter import get_secure_logger
    from ..core.health_checker import HealthChecker
    logger = get_secure_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

# Import tunnel system components
from .resilient_tunnel_broker import ResilientTunnelBroker
from .tailscale_farm_client import TailscaleFarmClient


class TunnelSystemManager:
    """Менеджер туннельной системы для EDGE устройств"""
    
    def __init__(self):
        self.tunnel_broker: Optional[ResilientTunnelBroker] = None
        self.farm_client: Optional[TailscaleFarmClient] = None
        self.health_checker: Optional[HealthChecker] = None
        self.is_running = False
        
        # Configuration from environment
        self.broker_config = {
            "host": os.getenv("TUNNEL_BROKER_HOST", "0.0.0.0"),
            "port": int(os.getenv("TUNNEL_BROKER_PORT", "8888")),
            "db_path": os.getenv("TUNNEL_BROKER_DB", "tunnel_broker.db")
        }
        
        self.farm_config = {
            "farm_id": os.getenv("FARM_ID", f"edge-farm-{int(time.time())}"),
            "farm_name": os.getenv("FARM_NAME", "EDGE КУБ-1063 Farm"),
            "owner_id": os.getenv("OWNER_ID", "edge_user"),
            "capabilities": ["kub1063", "monitoring", "control"],
            "api_port": int(os.getenv("FARM_API_PORT", "8080")),
            "location": os.getenv("FARM_LOCATION", "edge-device"),
        }
        
        self.tailscale_config = {
            "tailnet": os.getenv("TAILNET", "your-tailnet.ts.net"),
            "api_key": os.getenv("TAILSCALE_API_KEY", "tskey-api-xxx"),
        }
        
        self.discovery_url = os.getenv("DISCOVERY_SERVICE_URL", "http://localhost:8082")
        
        # Service mode selection
        self.service_mode = os.getenv("TUNNEL_SERVICE_MODE", "farm").lower()  # 'broker', 'farm', 'both'

    async def start_tunnel_broker(self):
        """Запуск туннельного брокера"""
        try:
            logger.info("🌐 Запуск Resilient Tunnel Broker...")
            self.tunnel_broker = ResilientTunnelBroker(
                host=self.broker_config["host"],
                port=self.broker_config["port"],
                db_path=self.broker_config["db_path"]
            )
            
            await self.tunnel_broker.start()
            logger.info(f"✅ Tunnel Broker запущен на {self.broker_config['host']}:{self.broker_config['port']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Tunnel Broker: {e}")
            raise

    async def start_farm_client(self):
        """Запуск клиента фермы"""
        try:
            logger.info("🚜 Запуск Tailscale Farm Client...")
            self.farm_client = TailscaleFarmClient(
                discovery_service_url=self.discovery_url,
                farm_config=self.farm_config,
                tailscale_config=self.tailscale_config
            )
            
            # Запускаем в отдельной задаче, так как он блокирующий
            asyncio.create_task(self.farm_client.start())
            await asyncio.sleep(2)  # Даем время на инициализацию
            
            logger.info("✅ Farm Client запущен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Farm Client: {e}")
            raise

    async def start_health_monitoring(self):
        """Запуск мониторинга здоровья системы"""
        try:
            self.health_checker = HealthChecker()
            
            # Добавляем компоненты для мониторинга
            if self.tunnel_broker:
                await self.health_checker.add_component(
                    "tunnel_broker",
                    self.tunnel_broker._health_check
                )
            
            if self.farm_client:
                def farm_health_check():
                    return {
                        "status": "healthy" if self.farm_client.is_registered else "degraded",
                        "registered": self.farm_client.is_registered,
                        "tailscale_ip": self.farm_client.tailscale_ip,
                        "last_heartbeat": self.farm_client.last_heartbeat,
                    }
                
                await self.health_checker.add_component("farm_client", farm_health_check)
            
            logger.info("✅ Health monitoring активирован")
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить health monitoring: {e}")

    async def start(self):
        """Запуск туннельной системы"""
        try:
            self.is_running = True
            logger.info("🚀 Запуск EDGE Tunnel System...")
            
            # Определяем какие сервисы запускать
            start_broker = self.service_mode in ["broker", "both"]
            start_farm = self.service_mode in ["farm", "both"]
            
            logger.info(f"📋 Режим работы: {self.service_mode.upper()}")
            logger.info(f"   - Tunnel Broker: {'✅' if start_broker else '❌'}")
            logger.info(f"   - Farm Client: {'✅' if start_farm else '❌'}")
            
            # Запускаем компоненты
            if start_broker:
                await self.start_tunnel_broker()
            
            if start_farm:
                await self.start_farm_client()
            
            # Запускаем мониторинг здоровья
            await self.start_health_monitoring()
            
            logger.info("✅ EDGE Tunnel System запущена успешно")
            
            # Показываем информацию о доступных эндпоинтах
            self._show_endpoints_info()
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска tunnel system: {e}")
            await self.stop()
            raise

    def _show_endpoints_info(self):
        """Показать информацию о доступных эндпоинтах"""
        logger.info("🔗 Доступные эндпоинты:")
        
        if self.tunnel_broker:
            broker_host = self.broker_config["host"]
            broker_port = self.broker_config["port"]
            logger.info(f"   📡 Tunnel Broker:")
            logger.info(f"      • Health: http://{broker_host}:{broker_port}/health")
            logger.info(f"      • Statistics: http://{broker_host}:{broker_port}/api/statistics")
            logger.info(f"      • Request Connection: POST http://{broker_host}:{broker_port}/api/request-connection")
        
        if self.farm_client:
            farm_port = self.farm_config["api_port"]
            logger.info(f"   🚜 Farm Client:")
            logger.info(f"      • Health: http://0.0.0.0:{farm_port}/health")
            logger.info(f"      • Current Data: http://0.0.0.0:{farm_port}/api/data/current")
            logger.info(f"      • Farm Info: http://0.0.0.0:{farm_port}/api/farm/info")
        
        if self.health_checker:
            logger.info(f"   💊 Health Check доступен через HealthChecker API")

    async def stop(self):
        """Остановка туннельной системы"""
        logger.info("🛑 Остановка EDGE Tunnel System...")
        
        self.is_running = False
        
        # Останавливаем компоненты
        if self.tunnel_broker:
            await self.tunnel_broker.stop()
            logger.info("   ✅ Tunnel Broker остановлен")
        
        if self.farm_client:
            # Farm client doesn't have explicit stop method, 
            # it will be stopped when the main loop exits
            logger.info("   ✅ Farm Client остановлен")
        
        logger.info("✅ EDGE Tunnel System остановлена")

    async def run_forever(self):
        """Запуск и ожидание бесконечно"""
        await self.start()
        
        try:
            logger.info("⚠️ Нажмите Ctrl+C для остановки")
            
            # Основной цикл мониторинга
            while self.is_running:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                
                # Логируем статистику
                if self.tunnel_broker:
                    try:
                        health = await self.tunnel_broker._health_check()
                        logger.debug(f"📊 Broker: {health.get('active_connections', 0)} connections, "
                                   f"{health.get('online_farms', 0)} farms")
                    except:
                        pass
                
                if self.farm_client and self.farm_client.is_registered:
                    logger.debug(f"🚜 Farm registered with IP: {self.farm_client.tailscale_ip}")
        
        except KeyboardInterrupt:
            logger.info("👋 Получен сигнал остановки")
        finally:
            await self.stop()


async def main():
    """Главная функция"""
    # Настройка обработчиков сигналов
    tunnel_manager = TunnelSystemManager()
    
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, остановка...")
        asyncio.create_task(tunnel_manager.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await tunnel_manager.run_forever()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await tunnel_manager.stop()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("🎯 EDGE Tunnel System Starter")
    logger.info("💡 Настройте переменные окружения:")
    logger.info("   - TUNNEL_SERVICE_MODE: broker/farm/both (default: farm)")
    logger.info("   - FARM_ID: уникальный ID фермы")
    logger.info("   - TAILNET: ваш Tailscale tailnet")
    logger.info("   - TAILSCALE_API_KEY: API ключ Tailscale")
    logger.info("   - DISCOVERY_SERVICE_URL: URL discovery service")
    
    asyncio.run(main())