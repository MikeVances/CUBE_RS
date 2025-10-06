#!/usr/bin/env python3
"""
Запуск EDGE Tunnel Client для интеграции с IXON-style tunnel system
EDGE устройство с серым IP регистрируется на брокере с белым IP
Пользователи подключаются через P2P туннели к EDGE устройству
"""

import asyncio
import logging
import os
import socket
import sys
from pathlib import Path

# Добавляем корень проекта в Python path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from core.tunnel_integration import start_edge_tunnel_client, is_tunnel_system_available
from core.log_filter import get_secure_logger
from core.logging_config import setup_basic_logging

# Настройка логирования
setup_basic_logging("tunnel_client.log")
logger = get_secure_logger(__name__)


def get_config_from_env() -> dict:
    """Получение конфигурации из переменных окружения"""
    return {
        # Tunnel Broker (сервер с белым IP)
        "broker_url": os.getenv("TUNNEL_BROKER_URL", "http://localhost:8080"),
        
        # Идентификация фермы
        "farm_id": os.getenv("FARM_ID", f"edge-{socket.gethostname()}"),
        "owner_id": os.getenv("OWNER_ID", "user_123456"),
        "farm_name": os.getenv("FARM_NAME", f"EDGE Farm {socket.gethostname()}"),
        
        # Локальный API сервер
        "local_port": int(os.getenv("EDGE_API_PORT", "8080")),
        "api_host": os.getenv("EDGE_API_HOST", "0.0.0.0")
    }


def print_usage():
    """Вывод справки по использованию"""
    print("""
🌐 EDGE TUNNEL CLIENT - IXON-STYLE P2P ИНТЕГРАЦИЯ

Интегрирует EDGE Remote Dashboard с существующей tunnel system для обеспечения
безопасного P2P доступа пользователей к EDGE устройствам через серый IP.

📋 ИСПОЛЬЗОВАНИЕ:
    python start_tunnel_client.py

🔧 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:
    TUNNEL_BROKER_URL   - URL сервера-брокера с белым IP (обязательно)
                         Пример: http://your-server.com:8080
    
    FARM_ID            - Уникальный ID фермы (по умолчанию: edge-hostname)
    OWNER_ID           - ID владельца фермы (обязательно для авторизации)
    FARM_NAME          - Название фермы (по умолчанию: EDGE Farm hostname)
    
    EDGE_API_PORT      - Порт локального API (по умолчанию: 8080)
    EDGE_API_HOST      - Хост локального API (по умолчанию: 0.0.0.0)

📊 АРХИТЕКТУРА IXON-STYLE:
    1. EDGE устройство (серый IP) регистрируется на брокере
    2. Пользователь заходит в веб-приложение
    3. Веб-приложение запрашивает у брокера адрес EDGE устройства
    4. Устанавливается прямой P2P туннель пользователь <-> EDGE
    5. Трафик идет напрямую, минуя брокер

🎯 ПРИМЕРЫ ЗАПУСКА:

    # Базовый запуск (локальный брокер)
    python start_tunnel_client.py

    # Продакшн запуск с внешним брокером
    export TUNNEL_BROKER_URL="http://your-domain.com:8080"
    export OWNER_ID="user_abc123"
    export FARM_NAME="Ферма Василия"
    python start_tunnel_client.py

    # Запуск с кастомным портом
    export EDGE_API_PORT="9090"
    export TUNNEL_BROKER_URL="http://broker.example.com:8080"
    python start_tunnel_client.py

🔗 ТРЕБОВАНИЯ:
    • tunnel_system в родительской директории
    • Работающий Tunnel Broker на сервере с белым IP
    • EDGE система с устройствами в config/devices.yaml

🌐 ПОСЛЕ ЗАПУСКА:
    • EDGE API доступен локально: http://localhost:8080
    • Ферма зарегистрирована в tunnel broker
    • Готов к P2P соединениям с пользователями
    • Heartbeat отправляется каждые 5 минут

📱 ДЛЯ ПОЛЬЗОВАТЕЛЕЙ:
    Откройте веб-приложение mobile_app на брокере,
    войдите под OWNER_ID и подключитесь к ферме
""")


async def main():
    """Основная функция запуска EDGE Tunnel Client"""
    logger.info("🌐 ЗАПУСК EDGE TUNNEL CLIENT")
    logger.info("=" * 60)
    
    # Проверяем доступность tunnel system
    if not is_tunnel_system_available():
        logger.error("❌ Tunnel System недоступна")
        logger.error("   Убедитесь что tunnel_system находится в родительской директории")
        logger.error("   и все зависимости установлены")
        return 1
    
    # Получаем конфигурацию
    config = get_config_from_env()
    
    # Валидация конфигурации
    if not config["broker_url"] or config["broker_url"] == "http://localhost:8080":
        logger.warning("⚠️ Используется локальный broker URL")
        logger.warning("   Для продакшн установите TUNNEL_BROKER_URL")
    
    if config["owner_id"] == "user_123456":
        logger.warning("⚠️ Используется тестовый OWNER_ID")
        logger.warning("   Для продакшн установите корректный OWNER_ID")
    
    logger.info(f"🔧 Конфигурация:")
    logger.info(f"   • Broker URL: {config['broker_url']}")
    logger.info(f"   • Farm ID: {config['farm_id']}")
    logger.info(f"   • Owner ID: {config['owner_id']}")
    logger.info(f"   • Farm Name: {config['farm_name']}")
    logger.info(f"   • Local API: {config['api_host']}:{config['local_port']}")
    
    try:
        logger.info("🚀 Запуск EDGE Tunnel Client...")
        logger.info("   📊 Функциональность:")
        logger.info("   • Регистрация в Tunnel Broker")
        logger.info("   • Периодический heartbeat")
        logger.info("   • P2P API прокси для EDGE Remote Dashboard")
        logger.info("   • Совместимость с mobile_app пользователей")
        
        # Запуск клиента (блокирующий вызов)
        await start_edge_tunnel_client(
            broker_url=config["broker_url"],
            farm_id=config["farm_id"],
            owner_id=config["owner_id"],
            farm_name=config["farm_name"],
            local_port=config["local_port"],
            api_host=config["api_host"]
        )
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал прерывания")
        logger.info("✅ EDGE Tunnel Client остановлен")
        return 0
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


def check_environment():
    """Проверка окружения перед запуском"""
    logger.info("🔍 Проверка окружения...")
    
    # Проверка tunnel_system
    parent_dir = Path(__file__).parent.parent
    tunnel_system_path = parent_dir / "tunnel_system"
    
    if not tunnel_system_path.exists():
        logger.error(f"❌ tunnel_system не найдена по пути: {tunnel_system_path}")
        logger.error("   Убедитесь что проект развернут правильно")
        return False
    
    logger.info(f"✅ tunnel_system найдена: {tunnel_system_path}")
    
    # Проверка EDGE компонентов
    required_modules = [
        "core.device_registry",
        "core.remote_dashboard",
        "core.tunnel_integration"
    ]
    
    for module in required_modules:
        try:
            __import__(module)
            logger.debug(f"✅ {module}")
        except ImportError as e:
            logger.error(f"❌ {module}: {e}")
            return False
    
    logger.info("✅ Все компоненты EDGE доступны")
    return True


if __name__ == "__main__":
    # Обработка аргументов командной строки
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h", "help"]:
            print_usage()
            sys.exit(0)
        elif sys.argv[1] == "check":
            success = check_environment()
            sys.exit(0 if success else 1)
    
    # Проверка окружения
    if not check_environment():
        logger.error("❌ Проверка окружения не пройдена")
        sys.exit(1)
    
    # Запуск основной функции
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)