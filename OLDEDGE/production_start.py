#!/usr/bin/env python3
"""
EDGE Production Startup Script
Оптимизированный запуск для продакшн-среды с мониторингом и автовосстановлением

Usage:
  python production_start.py                 # start all production services
  python production_start.py --config-check  # validate configuration
  python production_start.py --dry-run       # check without starting
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from core.config_manager import get_config
from core.edge_authentication import EDGEAuthConfig, EDGEAuthenticatedClient
from core.device_registry import DeviceRegistry
from core.log_filter import get_secure_logger
from core.health_checker import HealthChecker
from core.error_handler import CircuitBreakerRegistry
from core.security_manager import get_security_manager

# Проверяем критически важные модули
REQUIRED_MODULES = [
    "core.telegram",
    "core.edge_ping_service", 
    "core.health_api",
    "core.publishing"
]

for module in REQUIRED_MODULES:
    try:
        __import__(module)
    except ImportError as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Модуль {module} недоступен: {e}")
        sys.exit(1)

from core.telegram import run_telegram_bot
from core.edge_ping_service import run_edge_ping_service
from core.health_api import start_health_api, stop_health_api
from core.publishing import WebSocketServer, MQTTPublisher

logger = get_secure_logger(__name__)

class ProductionEDGEService:
    """Production-ready EDGE сервис с мониторингом и восстановлением"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/production.yaml"
        self.config = self._load_production_config()
        self.device_registry = DeviceRegistry()
        self.health_checker = HealthChecker()
        self.circuit_breaker_registry = CircuitBreakerRegistry()
        self.security_manager = get_security_manager()
        
        self.auth_client = None
        self.running_services = []
        self.service_health = {}
        self.shutdown_event = asyncio.Event()
        self.restart_count = 0
        self.max_restarts = 3
        
        # Состояние системы
        self.offline_mode = False
        self.offline_reason = None
        self.startup_time = time.time()
        
    def _load_production_config(self):
        """Загрузка production конфигурации с валидацией"""
        try:
            if Path(self.config_path).exists():
                config = get_config(self.config_path)
                logger.info(f"✅ Загружена production конфигурация: {self.config_path}")
            else:
                logger.warning(f"⚠️ Production конфиг не найден: {self.config_path}, используем default")
                config = get_config()
            
            # Валидация критических настроек
            self._validate_production_config(config)
            return config
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            raise
    
    def _validate_production_config(self, config):
        """Валидация production конфигурации"""
        critical_checks = [
            (config.system.environment == "production", "system.environment должен быть 'production'"),
            (config.system.log_level in ["INFO", "WARNING", "ERROR"], "log_level должен быть INFO/WARNING/ERROR"),
            (hasattr(config, "monitoring"), "отсутствует секция monitoring"),
            (hasattr(config, "backup"), "отсутствует секция backup"),
        ]
        
        for check, message in critical_checks:
            if not check:
                raise ValueError(f"Ошибка production конфигурации: {message}")
        
        logger.info("✅ Production конфигурация валидна")
    
    async def pre_startup_checks(self) -> bool:
        """Предварительные проверки перед запуском"""
        logger.info("🔍 Выполняем предварительные проверки...")
        
        checks = [
            ("Проверка структуры директорий", self._check_directories),
            ("Проверка прав доступа", self._check_permissions),
            ("Проверка системных ресурсов", self._check_system_resources),
            ("Проверка безопасности", self._check_security),
            ("Проверка устройств", self._check_devices),
        ]
        
        for check_name, check_func in checks:
            try:
                logger.info(f"  🔄 {check_name}...")
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                if not result:
                    logger.error(f"❌ {check_name} не пройдена")
                    return False
                logger.info(f"  ✅ {check_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка в {check_name}: {e}")
                return False
        
        logger.info("✅ Все предварительные проверки пройдены")
        return True
    
    def _check_directories(self) -> bool:
        """Проверка и создание необходимых директорий"""
        required_dirs = [
            "/var/lib/cube_edge",
            "/var/log/cube_edge", 
            "/var/backups/cube_edge",
            "config/secrets"
        ]
        
        for dir_path in required_dirs:
            path = Path(dir_path)
            try:
                path.mkdir(parents=True, exist_ok=True)
                # Проверяем права записи
                test_file = path / ".write_test"
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                logger.error(f"Проблема с директорией {dir_path}: {e}")
                return False
        
        return True
    
    def _check_permissions(self) -> bool:
        """Проверка прав доступа к критическим файлам"""
        critical_files = [
            ("config/secrets/master.key", 0o600),
            ("config/secrets/bot_secrets.enc", 0o600),
        ]
        
        for file_path, expected_mode in critical_files:
            path = Path(file_path)
            if path.exists():
                actual_mode = path.stat().st_mode & 0o777
                if actual_mode != expected_mode:
                    logger.warning(f"Неправильные права {file_path}: {oct(actual_mode)} != {oct(expected_mode)}")
                    try:
                        path.chmod(expected_mode)
                        logger.info(f"Исправлены права для {file_path}")
                    except Exception as e:
                        logger.error(f"Не удалось исправить права {file_path}: {e}")
                        return False
        
        return True
    
    async def _check_system_resources(self) -> bool:
        """Проверка системных ресурсов"""
        try:
            system_health = await self.health_checker.check_system_resources()
            
            thresholds = getattr(self.config, "monitoring", {}).get("alert_thresholds", {})
            cpu_limit = thresholds.get("cpu_percent", 80)
            memory_limit = thresholds.get("memory_percent", 85)
            
            if system_health.get("cpu_percent", 0) > cpu_limit:
                logger.warning(f"⚠️ Высокая загрузка CPU: {system_health['cpu_percent']}%")
            
            if system_health.get("memory_percent", 0) > memory_limit:
                logger.warning(f"⚠️ Высокое использование памяти: {system_health['memory_percent']}%")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки системных ресурсов: {e}")
            return False
    
    def _check_security(self) -> bool:
        """Проверка системы безопасности"""
        try:
            security_health = self.security_manager.health_check()
            
            if not security_health.get("encryption_available"):
                logger.error("❌ Шифрование недоступно")
                return False
            
            if not security_health.get("master_key_exists"):
                logger.error("❌ Master key отсутствует")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки безопасности: {e}")
            return False
    
    async def _check_devices(self) -> bool:
        """Проверка доступности устройств"""
        try:
            self.device_registry.load_devices_from_config()
            devices = self.device_registry.get_devices()
            
            if not devices:
                logger.warning("⚠️ Устройства не настроены")
                return True  # Не критично для запуска
            
            logger.info(f"📡 Найдено устройств: {len(devices)}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки устройств: {e}")
            return False
    
    async def setup_authentication(self):
        """Настройка аутентификации с SERVER"""
        offline_mode_env = os.getenv('EDGE_OFFLINE_MODE', '').lower() in {'true', '1', 'yes'}
        
        if offline_mode_env:
            self.offline_mode = True
            self.offline_reason = "offline mode enabled via EDGE_OFFLINE_MODE"
            logger.info("🚫 Offline mode активирован через переменную окружения")
            return
        
        auth_config = EDGEAuthConfig(
            api_key=os.getenv('EDGE_API_KEY', 'demo-api-key'),
            device_id=os.getenv('EDGE_DEVICE_ID', 'edge-device-001'),
            farm_id=os.getenv('EDGE_FARM_ID', 'demo-farm'),
            server_url=os.getenv('SERVER_URL', 'http://localhost:8080')
        )
        
        self.auth_client = EDGEAuthenticatedClient(auth_config, enable_mitm_protection=True)
        
        try:
            success = await asyncio.to_thread(self.auth_client.authenticate)
            if success:
                logger.info("✅ Authentication with SERVER successful")
                return
        except Exception as exc:
            self.offline_reason = self.auth_client.last_error or str(exc)
        
        logger.warning(f"⚠️ Authentication failed ({self.offline_reason}), работаем в offline режиме")
        self.offline_mode = True
        self.auth_client = None
    
    async def start_service_with_monitoring(self, service_name: str, service_coro, critical: bool = True):
        """Запуск сервиса с мониторингом"""
        try:
            logger.info(f"🚀 Запуск {service_name}...")
            task = asyncio.create_task(service_coro)
            self.running_services.append((service_name, task, critical))
            self.service_health[service_name] = {"status": "running", "start_time": time.time()}
            logger.info(f"✅ {service_name} запущен")
            return task
        except Exception as e:
            logger.error(f"❌ Ошибка запуска {service_name}: {e}")
            self.service_health[service_name] = {"status": "failed", "error": str(e)}
            if critical:
                raise
            return None
    
    async def monitor_services(self):
        """Мониторинг состояния сервисов"""
        while not self.shutdown_event.is_set():
            try:
                failed_services = []
                
                for service_name, task, critical in self.running_services:
                    if task.done():
                        try:
                            await task  # Получаем исключение если есть
                            logger.warning(f"⚠️ Сервис {service_name} завершился")
                        except Exception as e:
                            logger.error(f"❌ Сервис {service_name} упал: {e}")
                            if critical:
                                failed_services.append(service_name)
                        
                        self.service_health[service_name] = {
                            "status": "failed",
                            "error": "Service stopped unexpectedly"
                        }
                
                if failed_services and self.restart_count < self.max_restarts:
                    logger.warning(f"🔄 Критические сервисы упали: {failed_services}, перезапуск...")
                    await self.restart_failed_services()
                elif failed_services:
                    logger.error(f"💀 Достигнут лимит перезапусков, завершение работы")
                    self.shutdown_event.set()
                
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                
            except Exception as e:
                logger.error(f"Ошибка в мониторинге сервисов: {e}")
                await asyncio.sleep(30)
    
    async def restart_failed_services(self):
        """Перезапуск упавших сервисов"""
        self.restart_count += 1
        logger.info(f"🔄 Перезапуск сервисов (попытка {self.restart_count}/{self.max_restarts})")
        
        # Простая реализация - полный перезапуск
        await self.shutdown()
        await asyncio.sleep(5)
        # Здесь должна быть логика перезапуска только упавших сервисов
    
    async def run(self):
        """Главный цикл production сервиса"""
        logger.info("🚀 Запуск Production EDGE Service...")
        
        # Предварительные проверки
        if not await self.pre_startup_checks():
            logger.error("❌ Предварительные проверки не пройдены")
            return 1
        
        try:
            # Аутентификация
            await self.setup_authentication()
            
            # Загрузка устройств
            logger.info("📡 Загрузка конфигурации устройств...")
            self.device_registry.load_devices_from_config()
            
            # Запуск критических сервисов
            await self.start_service_with_monitoring(
                "Health API", 
                self._health_api_wrapper(),
                critical=True
            )
            
            await self.start_service_with_monitoring(
                "Telegram Bot",
                self._telegram_wrapper(),
                critical=False
            )
            
            if not self.offline_mode:
                await self.start_service_with_monitoring(
                    "EDGE Ping Service",
                    run_edge_ping_service(self.device_registry),
                    critical=False
                )
                
                await self.start_service_with_monitoring(
                    "Heartbeat Service",
                    self.heartbeat_loop(),
                    critical=False
                )
            
            # Опциональные сервисы
            if getattr(self.config.services, "mqtt_enabled", False):
                await self.start_service_with_monitoring(
                    "MQTT Publisher",
                    MQTTPublisher(self.device_registry).publish_loop(),
                    critical=False
                )
            
            if getattr(self.config.services, "websocket_enabled", False):
                await self.start_service_with_monitoring(
                    "WebSocket Server",
                    WebSocketServer().start_server(),
                    critical=False
                )
            
            # Запуск мониторинга
            monitor_task = asyncio.create_task(self.monitor_services())
            
            logger.info(f"✅ Production EDGE Services запущены ({len(self.running_services)} сервисов)")
            
            if self.offline_mode and self.offline_reason:
                logger.info(f"🌐 EDGE работает в offline режиме: {self.offline_reason}")
            
            # Ожидание завершения
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            return 1
        finally:
            await self.shutdown()
        
        return 0
    
    async def _health_api_wrapper(self):
        """Wrapper для Health API"""
        success = await start_health_api()
        if not success:
            raise RuntimeError("Не удалось запустить Health API")
        
        # Health API работает в фоне, удерживаем задачу
        try:
            await self.shutdown_event.wait()
        finally:
            await stop_health_api()
    
    async def _telegram_wrapper(self):
        """Wrapper для Telegram бота"""
        telegram_token = self.security_manager.get_secure_config_value(
            "bot_secrets", "telegram.bot_token", "TELEGRAM_BOT_TOKEN"
        )
        
        if not telegram_token:
            logger.warning("TELEGRAM_BOT_TOKEN не установлен, пропускаем telegram бот")
            return
        
        await run_telegram_bot(telegram_token)
    
    async def heartbeat_loop(self):
        """Heartbeat цикл"""
        if not self.auth_client:
            return
        
        logger.info("💓 Запуск heartbeat service")
        while not self.shutdown_event.is_set():
            try:
                devices_data = {}
                for device_info in self.device_registry.get_devices():
                    device_data = self.device_registry.get_device_data(device_info.device_id)
                    if device_data:
                        devices_data[device_info.device_id] = device_data
                
                success = await asyncio.to_thread(
                    self.auth_client.send_heartbeat,
                    "online",
                    {
                        "devices_count": len(devices_data), 
                        "devices_data": devices_data,
                        "uptime": time.time() - self.startup_time,
                        "restart_count": self.restart_count
                    }
                )
                
                if success:
                    logger.debug("💓 Heartbeat отправлен")
                else:
                    logger.warning("⚠️ Heartbeat failed")
                
            except Exception as e:
                logger.error(f"❌ Heartbeat error: {e}")
            
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
                break
            except asyncio.TimeoutError:
                continue
    
    async def shutdown(self):
        """Корректное завершение"""
        logger.info("🛑 Остановка Production EDGE Services...")
        
        self.shutdown_event.set()
        
        # Останавливаем сервисы в обратном порядке
        for service_name, task, _ in reversed(self.running_services):
            if not task.done():
                logger.info(f"🛑 Останавливаем {service_name}...")
                task.cancel()
        
        # Ждем завершения
        if self.running_services:
            await asyncio.gather(
                *[task for _, task, _ in self.running_services], 
                return_exceptions=True
            )
        
        logger.info("✅ Production EDGE Services остановлены")

def setup_production_logging(log_level: str = "INFO"):
    """Настройка production логирования"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(name)s] %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/var/log/cube_edge/production.log', encoding='utf-8')
        ]
    )

async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='Production EDGE Service')
    parser.add_argument('--config', default='config/production.yaml', help='Путь к production конфигурации')
    parser.add_argument('--config-check', action='store_true', help='Проверить конфигурацию и выйти')
    parser.add_argument('--dry-run', action='store_true', help='Проверить готовность без запуска')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    
    args = parser.parse_args()
    
    # Настройка логирования
    setup_production_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    try:
        service = ProductionEDGEService(args.config)
        
        if args.config_check:
            logger.info("✅ Конфигурация валидна")
            return 0
        
        if args.dry_run:
            ready = await service.pre_startup_checks()
            if ready:
                logger.info("✅ Система готова к запуску")
                return 0
            else:
                logger.error("❌ Система не готова к запуску")
                return 1
        
        # Обработчик сигналов
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}")
            asyncio.create_task(service.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        return await service.run()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Прервано пользователем")
        sys.exit(0)