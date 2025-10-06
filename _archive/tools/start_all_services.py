#!/usr/bin/env python3
"""
Запуск всех сервисов системы КУБ-1063
Использует централизованный конфиг-менеджер для настроек
"""

import logging
import os
import signal
import subprocess
import sys
import time

# Добавляем корень проекта в путь для импорта конфиг-менеджера
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Импорт конфиг-менеджера
try:
    from core.config_manager import get_config

    config = get_config()
except ImportError:
    print("❌ Не удалось импортировать ConfigManager. Убедитесь что установлен PyYAML.")
    sys.exit(1)

# Настройка логирования из конфига
log_file = config.config_dir / "logs" / "start_services.log"
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.system.log_level),
    format="%(asctime)s %(levelname)s [START] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

BANNER = (
    "🎯 Запуск всех сервисов системы КУБ-1063 (централизованная конфигурация)...\n"
    + "=" * 75
)


# Динамическое формирование списка сервисов из конфига
def get_enabled_services():
    """Возвращает список включенных сервисов из конфигурации"""
    services = []

    # Gateway (основной шлюз) - используем TypedModbusGateway
    if config.services.gateway_enabled:
        services.append(
            {
                "name": f"TypedModbusGateway (HTTP API {config.modbus_tcp.port})",
                "cmd": f"{sys.executable} apps/gateway/start_typed_gateway.py",
                "delay": 3,
            }
        )

    # Dashboard (Streamlit)
    if config.services.dashboard_enabled:
        services.append(
            {
                "name": f"Dashboard (Streamlit {config.services.dashboard_port})",
                "cmd": f"streamlit run dashboard/app.py --server.port {config.services.dashboard_port}",
                "delay": 1,
            }
        )

    # Telegram Bot
    if config.services.telegram_enabled:
        services.append(
            {
                "name": "Telegram Bot",
                "cmd": f"{sys.executable} telegram_bot/async_bot_main.py",
                "delay": 1,
            }
        )

    # WebSocket Server (если включен)
    if config.services.websocket_enabled:
        services.append(
            {
                "name": f"WebSocket Server ({config.services.websocket_port})",
                "cmd": f"{sys.executable} publish/websocket_server.py",
                "delay": 1,
            }
        )

    # MQTT Publisher (если включен)
    if config.services.mqtt_enabled:
        services.append(
            {
                "name": "MQTT Publisher",
                "cmd": f"{sys.executable} publish/mqtt.py",
                "delay": 1,
            }
        )

    return services


SERVICES = get_enabled_services()


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
                    logging.info(f"✅ {name} готов к работе")
                    return True
        except:
            pass
        time.sleep(1)

    logging.warning(f"⚠️ {name} не отвечает через {timeout}с")
    return False


def main():
    print(BANNER)
    print(f"📂 Рабочая директория: {ROOT_DIR}")

    # Проверяем доступность ключевых портов
    # Формируем список портов для проверки из конфига
    ports_to_check = []
    if config.services.gateway_enabled:
        ports_to_check.append(config.modbus_tcp.port)
    if config.services.dashboard_enabled:
        ports_to_check.append(config.services.dashboard_port)
    if config.services.websocket_enabled:
        ports_to_check.append(config.services.websocket_port)
    for port in ports_to_check:
        if not check_port_available(port):
            logging.error(f"❌ Порт {port} уже занят!")
            return 1

    # Настройка окружения
    env = os.environ.copy()
    env["PYTHONPATH"] = f".:{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"  # Для немедленного вывода логов

    processes = []

    try:
        # Запуск сервисов
        for service in SERVICES:
            name = service["name"]
            cmd = service["cmd"]
            delay = service.get("delay", 1)
            optional = service.get("optional", False)

            try:
                logging.info(f"🚀 Запуск {name}...")

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

                processes.append(
                    {"name": name, "process": process, "optional": optional}
                )

                logging.info(f"✅ {name} запущен (PID: {process.pid})")

                # Пауза между запусками
                if delay > 0:
                    time.sleep(delay)

            except Exception as e:
                error_msg = f"❌ Ошибка запуска {name}: {e}"
                if optional:
                    logging.warning(f"⚠️ {error_msg} (необязательный сервис)")
                else:
                    logging.error(error_msg)
                    if not optional:
                        raise

        # Проверяем готовность ключевых сервисов
        service_checks = []
        if config.services.gateway_enabled:
            service_checks.append(("Gateway", config.modbus_tcp.port))
        if config.services.dashboard_enabled:
            service_checks.append(("Dashboard", config.services.dashboard_port))
        if config.services.websocket_enabled:
            service_checks.append(("WebSocket", config.services.websocket_port))

        for name, port in service_checks:
            wait_for_service(name, port, timeout=15)

        # Выводим информацию о запущенных сервисах
        print("\n" + "=" * 70)
        print("✅ Система КУБ-1063 запущена (централизованная конфигурация)!")
        print("=" * 70)

        if config.services.dashboard_enabled:
            print(
                f"📊 Dashboard:        http://localhost:{config.services.dashboard_port}"
            )

        if config.services.gateway_enabled:
            print(f"🔧 Modbus TCP:       localhost:{config.modbus_tcp.port}")

        if config.services.websocket_enabled:
            print(
                f"🌐 WebSocket:        ws://localhost:{config.services.websocket_port}"
            )

        if config.services.telegram_enabled:
            print("🤖 Telegram Bot:     активен")

        if config.services.mqtt_enabled:
            print("📡 MQTT Publisher:   активен")

        print("=" * 70)
        print("📋 Логи сервисов:")
        print(
            f"   logs/gateway1.log      - основной шлюз (RS485→БД→Modbus TCP {config.modbus_tcp.port})"
        )
        print(
            f"   logs/dashboard.log     - веб-дашборд (порт {config.services.dashboard_port})"
        )
        print("   logs/telegram.log      - telegram bot")
        print("   logs/start_services.log - этот скрипт")
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
                    logging.error(
                        f"❌ {service['name']} неожиданно завершился (код: {proc.returncode})"
                    )
                    if not service["optional"]:
                        raise Exception(
                            f"Критический сервис {service['name']} завершился"
                        )

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")

    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")

    finally:
        # Остановка всех процессов
        print("\n🔄 Остановка всех сервисов...")

        # Сначала мягко останавливаем
        for service in reversed(processes):
            name = service["name"]
            proc = service["process"]

            if proc.poll() is None:
                try:
                    logging.info(f"🛑 Остановка {name}...")

                    if "Streamlit" in name:
                        # Streamlit лучше останавливать через SIGINT
                        proc.send_signal(signal.SIGINT)
                    else:
                        proc.terminate()

                except Exception as e:
                    logging.error(f"❌ Ошибка остановки {name}: {e}")

        # Ждем завершения с таймаутом
        deadline = time.time() + 10
        for service in reversed(processes):
            name = service["name"]
            proc = service["process"]

            if proc.poll() is None:
                try:
                    remaining = max(0, deadline - time.time())
                    proc.wait(timeout=remaining)
                    logging.info(f"✅ {name} остановлен")
                except subprocess.TimeoutExpired:
                    # Принудительная остановка
                    try:
                        proc.kill()
                        proc.wait(timeout=5)
                        logging.info(f"💀 {name} принудительно остановлен")
                    except:
                        logging.error(f"❌ Не удалось остановить {name}")
                except KeyboardInterrupt:
                    # Повторный Ctrl+C - принудительно убиваем все
                    logging.warning(
                        "⚡ Повторный Ctrl+C - принудительная остановка всех процессов"
                    )
                    try:
                        proc.kill()
                    except:
                        pass

        print("✅ Все сервисы остановлены")
        return 0


if __name__ == "__main__":
    sys.exit(main())
