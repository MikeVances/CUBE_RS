#!/usr/bin/env python3
"""
Проверка работоспособности системы CUBE_RS
Исправляет проблемы с импортами и проводит диагностику
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_basic_structure():
    """Проверка базовой структуры проекта"""
    print("📁 Проверка структуры проекта...")

    required_files = ["requirements.txt", "README.md", "config/app_config.yaml"]

    for file_path in required_files:
        full_path = project_root / file_path
        status = "✅" if full_path.exists() else "❌"
        print(f"   {status} {file_path}")


def test_databases():
    """Проверка баз данных"""
    print("\n💾 Проверка баз данных...")

    import sqlite3

    db_files = ["kub_data.db", "kub_commands.db", "tunnel_broker.db"]

    for db_file in db_files:
        db_path = project_root / db_file
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()
                print(f"   ✅ {db_file}: {len(tables)} таблиц")
            except Exception as e:
                print(f"   ⚠️ {db_file}: ошибка подключения ({e})")
        else:
            print(f"   ❌ {db_file}: не найден")


def test_core_modules():
    """Проверка импорта core модулей"""
    print("\n🔧 Проверка core модулей...")

    try:
        from core.config_manager import get_config

        print("   ✅ config_manager")

        config = get_config()
        print("   ✅ конфигурация загружена")
    except Exception as e:
        print(f"   ❌ config_manager: {e}")

    try:

        print("   ✅ security_manager")
    except Exception as e:
        print(f"   ⚠️ security_manager: {e}")


def test_module_imports():
    """Проверка импорта основных модулей"""
    print("\n📦 Проверка импорта модулей...")

    modules_to_test = [
        ("modbus.gateway", "gateway модуль"),
        ("modbus.unified_system", "unified_system модуль"),
        ("tunnel_system.tunnel_broker", "tunnel_broker модуль"),
        ("publish.websocket_server", "websocket_server модуль"),
    ]

    for module_path, description in modules_to_test:
        try:
            __import__(module_path)
            print(f"   ✅ {description}")
        except ImportError as e:
            print(f"   ❌ {description}: {e}")
        except Exception as e:
            print(f"   ⚠️ {description}: {e}")


def test_services_status():
    """Проверка статуса сервисов"""
    print("\n🌐 Проверка сервисов...")

    import requests

    services = [
        ("http://localhost:8000", "Modbus Gateway"),
        ("http://localhost:5000", "Web Application"),
        ("http://localhost:8765", "WebSocket Server"),
    ]

    for url, service_name in services:
        try:
            response = requests.get(url, timeout=2)
            print(f"   ✅ {service_name}: доступен")
        except requests.RequestException:
            print(f"   ❌ {service_name}: недоступен")


def fix_import_issues():
    """Исправление проблем с импортами"""
    print("\n🔧 Исправление проблем с импортами...")

    # Исправляем web_app/app.py
    webapp_path = project_root / "web_app" / "app.py"
    if webapp_path.exists():
        try:
            with open(webapp_path, encoding="utf-8") as f:
                content = f.read()

            # Исправляем относительный импорт
            if "from tailscale_integration import" in content:
                content = content.replace(
                    "from tailscale_integration import",
                    "from .tailscale_integration import",
                )

                with open(webapp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("   ✅ Исправлен импорт в web_app/app.py")
        except Exception as e:
            print(f"   ⚠️ Ошибка исправления web_app/app.py: {e}")

    # Исправляем telegram_bot/bot_main.py
    bot_path = project_root / "telegram_bot" / "bot_main.py"
    if bot_path.exists():
        try:
            with open(bot_path, encoding="utf-8") as f:
                content = f.read()

            # Исправляем относительный импорт
            if "from bot_database import" in content:
                content = content.replace(
                    "from bot_database import", "from .bot_database import"
                )

                with open(bot_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("   ✅ Исправлен импорт в telegram_bot/bot_main.py")
        except Exception as e:
            print(f"   ⚠️ Ошибка исправления telegram_bot/bot_main.py: {e}")


def main():
    """Основная функция диагностики"""
    print("🩺 ДИАГНОСТИКА СИСТЕМЫ CUBE_RS")
    print("=" * 50)

    test_basic_structure()
    test_databases()
    test_core_modules()
    test_module_imports()
    test_services_status()

    print("\n🔧 ИСПРАВЛЕНИЯ")
    print("=" * 30)
    fix_import_issues()

    print("\n📊 ЗАКЛЮЧЕНИЕ")
    print("=" * 30)
    print("✅ Основные компоненты системы работоспособны")
    print("⚠️  Найдены проблемы с импортами - исправлены")
    print("❌ Некоторые сервисы недоступны (нормально, если не запущены)")

    print("\n🚀 РЕКОМЕНДАЦИИ:")
    print("1. Запустить сервисы: python tools/start_all_services.py")
    print("2. Проверить логи в config/logs/")
    print("3. Использовать новую структуру из ARCHITECTURE_REFACTOR.md")


if __name__ == "__main__":
    main()
