#!/usr/bin/env python3
"""
Запуск удаленного дашборда через Tailscale для EDGE системы
Tailscale = транспорт, Remote Dashboard = функциональность
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Добавляем корень проекта в Python path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from core.remote_dashboard import get_dashboard_api
from core.tailscale_integration import is_tailscale_available
from core.log_filter import get_secure_logger
from core.logging_config import setup_basic_logging

# Настройка логирования
setup_basic_logging("tailscale.log")
logger = get_secure_logger(__name__)


def main():
    """Основная функция запуска Remote Dashboard через Tailscale"""
    logger.info("🌐 ЗАПУСК REMOTE DASHBOARD ДЛЯ EDGE СИСТЕМЫ")
    logger.info("=" * 60)
    
    # Проверяем переменные окружения
    farm_name = os.getenv("FARM_NAME", "EDGE Farm")  
    port = int(os.getenv("TAILSCALE_PORT", "8080"))
    
    # Проверяем доступность Tailscale (опционально)
    if is_tailscale_available():
        logger.info("✅ Tailscale система доступна (расширенные функции)")
    else:
        logger.warning("⚠️ Tailscale система недоступна (базовый режим)")
    
    logger.info(f"🔧 Конфигурация:")
    logger.info(f"   • Farm Name: {farm_name}")
    logger.info(f"   • HTTP Port: {port}")
    logger.info(f"   • Режим: {'Tailscale VPN' if is_tailscale_available() else 'Local Network'}")
    
    try:
        # Инициализация Remote Dashboard API
        dashboard = get_dashboard_api()
        logger.info("✅ Remote Dashboard API инициализирован")
        
        # Запуск HTTP сервера
        logger.info(f"🚀 Запуск HTTP сервера на порту {port}...")
        logger.info("   📊 Доступные endpoints:")
        logger.info("   • GET / - веб интерфейс дашборда")
        logger.info("   • GET /api/health - проверка состояния")
        logger.info("   • GET /api/devices - список устройств")
        logger.info("   • GET /api/devices/status - статус всех устройств")
        logger.info("   • GET /api/device/<id> - детали устройства")
        logger.info("   • GET /api/alarms - активные аварии")
        
        if is_tailscale_available():
            logger.info("🔒 Доступ через Tailscale VPN:")
            logger.info("   • Найдите IP устройства: tailscale ip") 
            logger.info(f"   • Откройте: http://100.x.x.x:{port}")
        else:
            logger.info(f"🌐 Локальный доступ: http://localhost:{port}")
        
        # Запуск Flask приложения (блокирующий вызов)
        dashboard.run(host='0.0.0.0', port=port, debug=False)
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал прерывания")
        logger.info("✅ Remote Dashboard остановлен")
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
        "core.device_adapters", 
        "core.tailscale_integration"
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


def print_usage():
    """Вывод справки по использованию"""
    print("""
🌐 TAILSCALE ИНТЕГРАЦИЯ ДЛЯ EDGE СИСТЕМЫ

Предоставляет HTTP API для удаленного доступа к данным КУБ устройств
через защищенную mesh-сеть Tailscale.

📋 ИСПОЛЬЗОВАНИЕ:
    python start_tailscale.py

🔧 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:
    TAILSCALE_API_KEY - API ключ Tailscale (обязательно для полного функционала)
    TAILSCALE_TAILNET - имя tailnet (по умолчанию: your-tailnet.ts.net)  
    FARM_NAME - название фермы (по умолчанию: EDGE Farm)
    FARM_LOCATION - местоположение фермы
    TAILSCALE_PORT - порт HTTP API (по умолчанию: 8080)

📊 API ENDPOINTS:
    GET /api/farm/data - полные данные всех устройств
    GET /api/farm/summary - краткая сводка по ферме
    GET /api/device/<id> - данные конкретного устройства
    GET /api/health - проверка состояния сервиса

🔗 ТРЕБОВАНИЯ:
    • tunnel_system в родительской директории
    • Tailscale установлен на системе
    • EDGE система с устройствами в config/devices.yaml

🎯 ПРИМЕРЫ:
    # Запуск с API ключом
    export TAILSCALE_API_KEY="your-api-key"
    export FARM_NAME="Ферма Василия"
    python start_tailscale.py
    
    # Проверка доступности через Tailscale IP
    curl http://100.x.x.x:8080/api/health
    curl http://100.x.x.x:8080/api/farm/summary
""")


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
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)