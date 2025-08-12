#!/usr/bin/env python3
"""
Запуск всех сервисов системы КУБ-1063
Исправленная версия для корректной работы двух шлюзов
"""

import os
import sys
import time
import signal
import subprocess
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [START] %(message)s",
    handlers=[
        logging.FileHandler("start_services.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Корневая директория проекта
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNER = (
    "🎯 Запуск всех сервисов системы КУБ-1063...\n" +
    "=" * 60
)

# Список сервисов в порядке запуска
SERVICES = [
    # Сначала запускаем основной шлюз (читает RS485 и пишет в БД)
    {
        "name": "Gateway 1 (Modbus TCP + DB)",
        "cmd": f"{sys.executable} -m modbus.gateway",
        "delay": 2  # Задержка после запуска
    },
    # Затем дополнительный шлюз (читает из БД и предоставляет Modbus TCP на 5022)
    {
        "name": "Gateway 2 (Modbus TCP 5022)",
        "cmd": f"{sys.executable} -m modbus.gateway2",
        "delay": 1
    },
    # Дашборд
    {
        "name": "Dashboard (Streamlit)",
        "cmd": "streamlit run dashboard/app.py --server.port 8501",
        "delay": 1
    },
    # Telegram бот (если есть)
    {
        "name": "Telegram Bot",
        "cmd": f"{sys.executable} start_bot.py" ,
        "delay": 0.5,
        "optional": True  # Необязательный сервис
    }
]


def check_port_available(port):
    """Проверка доступности порта"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', port))
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
                result = s.connect_ex(('localhost', port))
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
    ports_to_check = [5021, 5022, 8501]
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
                    universal_newlines=True
                )
                
                processes.append({
                    "name": name,
                    "process": process,
                    "optional": optional
                })
                
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
        service_checks = [
            ("Gateway 1", 5021),
            ("Gateway 2", 5022),
            ("Dashboard", 8501)
        ]
        
        for name, port in service_checks:
            wait_for_service(name, port, timeout=15)
        
        # Выводим информацию о запущенных сервисах
        print("\n" + "=" * 60)
        print("✅ Система КУБ-1063 запущена!")
        print("=" * 60)
        print("📊 Дашборд:          http://localhost:8501")
        print("🔧 Modbus TCP 1:       localhost:5021 (основной)")
        print("🔧 Modbus TCP 2:       localhost:5022 (дубликат)")
        print("📡 Оба порта содержат одинаковые регистры КУБ-1063")
        print("🤖 Telegram Bot:     активен (если запущен)")
        print("=" * 60)
        print("📋 Логи сервисов:")
        print("   gateway1.log  - основной шлюз (RS485→БД→Modbus TCP 5021)")
        print("   gateway2.log  - дубликат шлюза (БД→Modbus TCP 5022)")
        print("   start_services.log - этот скрипт")
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
                    logging.error(f"❌ {service['name']} неожиданно завершился (код: {proc.returncode})")
                    if not service["optional"]:
                        raise Exception(f"Критический сервис {service['name']} завершился")
    
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
                    logging.warning("⚡ Повторный Ctrl+C - принудительная остановка всех процессов")
                    try:
                        proc.kill()
                    except:
                        pass
        
        print("✅ Все сервисы остановлены")
        return 0


if __name__ == "__main__":
    sys.exit(main())