#!/usr/bin/env python3
"""
SERVER: Запуск всех сервисов системы CUBE_RS SERVER
Управляет веб-приложением, туннельным брокером и системой мониторинга
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Настройка путей для SERVER
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Настройка логирования
log_dir = ROOT_DIR / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / "start_services.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [SERVER-START] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"), 
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

BANNER = (
    "🎯 Запуск всех сервисов CUBE_RS SERVER...\n"
    + "=" * 75
)

def get_server_services():
    """Возвращает список SERVER сервисов"""
    services = []

    # Web Application (Flask/Gunicorn)
    services.append({
        "name": "Web Application (Flask)",
        "cmd": f"{sys.executable} web_app/app.py",
        "delay": 2,
        "port": 8080,
        "critical": True
    })

    # Tunnel Broker
    services.append({
        "name": "Resilient Tunnel Broker",
        "cmd": f"{sys.executable} resilient_tunnel_broker.py",
        "delay": 2,
        "port": 8081,
        "critical": True
    })

    # Security Monitor
    services.append({
        "name": "Security Monitor",
        "cmd": f"{sys.executable} monitoring/security_monitor.py",
        "delay": 1,
        "optional": True
    })

    # Network Security Monitor
    services.append({
        "name": "Network Security Monitor",
        "cmd": f"{sys.executable} monitoring/network_security_monitor.py",
        "delay": 1,
        "optional": True
    })

    return services

SERVICES = get_server_services()

def check_port_available(port):
    """Проверка доступности порта"""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", port))
            return True
    except:
        return False

def wait_for_service(name, port, timeout=30):
    """Ожидание готовности сервиса"""
    import socket

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("localhost", port))
                if result == 0:
                    logger.info(f"✅ {name} готов к работе")
                    return True
        except:
            pass
        time.sleep(1)

    logger.warning(f"⚠️ {name} не отвечает через {timeout}с")
    return False

def check_dependencies():
    """Проверка зависимостей SERVER"""
    logger.info("📦 Проверка зависимостей SERVER...")
    
    required_files = [
        "web_app/app.py",
        "web_app/api_gateway.py", 
        "web_app/rbac_system.py",
        "resilient_tunnel_broker.py",
        "monitoring/security_monitor.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = ROOT_DIR / file_path
        if not full_path.exists():
            missing_files.append(file_path)
        else:
            logger.info(f"   ✅ {file_path}")
    
    if missing_files:
        logger.error(f"❌ Отсутствуют критические файлы: {missing_files}")
        return False
    
    return True

def setup_environment():
    """Настройка окружения SERVER"""
    env = os.environ.copy()
    
    # Настройки Python
    env["PYTHONPATH"] = f"{ROOT_DIR}:{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"
    
    # Настройки Flask для SERVER
    env["FLASK_ENV"] = "production"
    env["FLASK_DEBUG"] = "0"
    
    # Настройки SERVER
    env["SERVER_HOST"] = "0.0.0.0"
    env["SERVER_PORT"] = "8080"
    env["TUNNEL_BROKER_PORT"] = "8081"
    
    # Пути к данным
    env["SERVER_DATA_DIR"] = str(ROOT_DIR / "data")
    env["SERVER_LOG_DIR"] = str(ROOT_DIR / "logs")
    env["SERVER_CONFIG_DIR"] = str(ROOT_DIR / "config")
    
    return env

def main():
    print(BANNER)
    logger.info(f"📂 SERVER Root: {ROOT_DIR}")

    # Проверяем зависимости
    if not check_dependencies():
        logger.error("❌ Проверка зависимостей не пройдена")
        return 1

    # Проверяем доступность ключевых портов
    ports_to_check = [8080, 8081]  # Web App, Tunnel Broker
    for port in ports_to_check:
        if not check_port_available(port):
            logger.error(f"❌ Порт {port} уже занят!")
            return 1

    # Настройка окружения
    env = setup_environment()

    # Создаем необходимые директории
    for directory in ["data", "logs", "config"]:
        (ROOT_DIR / directory).mkdir(exist_ok=True)

    processes = []

    try:
        # Запуск сервисов
        for service in SERVICES:
            name = service["name"]
            cmd = service["cmd"]
            delay = service.get("delay", 1)
            optional = service.get("optional", False)
            critical = service.get("critical", False)

            try:
                logger.info(f"🚀 Запуск {name}...")

                # Запускаем процесс
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    env=env,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                )

                processes.append({
                    "name": name,
                    "process": process,
                    "optional": optional,
                    "critical": critical
                })

                logger.info(f"✅ {name} запущен (PID: {process.pid})")

                # Пауза между запусками
                if delay > 0:
                    time.sleep(delay)

            except Exception as e:
                error_msg = f"❌ Ошибка запуска {name}: {e}"
                if optional:
                    logger.warning(f"⚠️ {error_msg} (необязательный сервис)")
                else:
                    logger.error(error_msg)
                    if critical:
                        raise

        # Проверяем готовность критических сервисов
        critical_services = [
            ("Web Application", 8080),
            ("Tunnel Broker", 8081)
        ]

        for name, port in critical_services:
            wait_for_service(name, port, timeout=20)

        # Выводим информацию о запущенных сервисах
        print("\n" + "=" * 70)
        print("✅ CUBE_RS SERVER система запущена!")
        print("=" * 70)

        print("🌐 Web Application:    http://localhost:8080")
        print("🔗 Tunnel Broker:      ws://localhost:8081")  
        print("🛡️  Security Monitor:   активен")
        print("📡 Network Monitor:    активен")

        print("=" * 70)
        print("📋 Логи сервисов:")
        print("   logs/webapp.log           - веб-приложение")
        print("   logs/tunnel_broker.log    - туннельный брокер")
        print("   logs/security_monitor.log - мониторинг безопасности")
        print("   logs/start_services.log   - этот скрипт")
        print("=" * 60)
        print("⚠️  Нажмите Ctrl+C для остановки всех сервисов")
        print("=" * 60)

        # Мониторим процессы
        while True:
            time.sleep(5)

            # Проверяем состояние процессов
            for service in processes:
                proc = service["process"]
                if proc.poll() is not None:
                    # Процесс завершился
                    logger.error(
                        f"❌ {service['name']} неожиданно завершился (код: {proc.returncode})"
                    )
                    if service["critical"]:
                        raise Exception(
                            f"Критический сервис {service['name']} завершился"
                        )

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")

    finally:
        # Остановка всех процессов
        print("\n🔄 Остановка всех SERVER сервисов...")

        # Сначала мягко останавливаем
        for service in reversed(processes):
            name = service["name"]
            proc = service["process"]

            if proc.poll() is None:
                try:
                    logger.info(f"🛑 Остановка {name}...")
                    proc.terminate()
                except Exception as e:
                    logger.error(f"❌ Ошибка остановки {name}: {e}")

        # Ждем завершения с таймаутом
        deadline = time.time() + 10
        for service in reversed(processes):
            name = service["name"]
            proc = service["process"]

            if proc.poll() is None:
                try:
                    remaining = max(0, deadline - time.time())
                    proc.wait(timeout=remaining)
                    logger.info(f"✅ {name} остановлен")
                except subprocess.TimeoutExpired:
                    # Принудительная остановка
                    try:
                        proc.kill()
                        proc.wait(timeout=5)
                        logger.info(f"💀 {name} принудительно остановлен")
                    except:
                        logger.error(f"❌ Не удалось остановить {name}")
                except KeyboardInterrupt:
                    # Повторный Ctrl+C - принудительно убиваем все
                    logger.warning(
                        "⚡ Повторный Ctrl+C - принудительная остановка всех процессов"
                    )
                    try:
                        proc.kill()
                    except:
                        pass

        print("✅ Все SERVER сервисы остановлены")
        return 0


if __name__ == "__main__":
    sys.exit(main())