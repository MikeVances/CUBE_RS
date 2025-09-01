#!/usr/bin/env python3
"""
Скрипт для локального тестирования Tunnel System
Запускает все компоненты на одной машине для демонстрации
"""

import os
import sys
import time
import subprocess
import threading
import signal
import requests
from typing import List, Dict

# Глобальный список процессов для остановки
processes: List[subprocess.Popen] = []

def signal_handler(signum, frame):
    """Обработчик сигнала для graceful shutdown"""
    print("\n🛑 Получен сигнал остановки, завершаем процессы...")
    stop_all_processes()
    sys.exit(0)

def stop_all_processes():
    """Остановка всех запущенных процессов"""
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            print(f"✅ Процесс {proc.pid} остановлен")
        except subprocess.TimeoutExpired:
            proc.kill()
            print(f"💀 Процесс {proc.pid} принудительно завершен")
        except Exception as e:
            print(f"❌ Ошибка остановки процесса {proc.pid}: {e}")

def run_process(name: str, command: List[str], cwd: str = None) -> subprocess.Popen:
    """Запуск процесса с логированием"""
    print(f"🚀 Запуск {name}...")
    print(f"   Команда: {' '.join(command)}")
    
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=cwd
        )
        processes.append(proc)
        
        # Запускаем вывод логов в отдельном потоке
        def log_output():
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                print(f"[{name}] {line.strip()}")
        
        log_thread = threading.Thread(target=log_output, daemon=True)
        log_thread.start()
        
        return proc
        
    except Exception as e:
        print(f"❌ Ошибка запуска {name}: {e}")
        return None

def wait_for_service(url: str, timeout: int = 30) -> bool:
    """Ожидание готовности сервиса"""
    print(f"⏳ Ожидание готовности {url}...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ Сервис {url} готов")
                return True
        except:
            pass
        
        time.sleep(2)
    
    print(f"❌ Сервис {url} не готов за {timeout} секунд")
    return False

def register_test_user() -> str:
    """Регистрация тестового пользователя"""
    print("👤 Регистрация тестового пользователя...")
    
    try:
        response = requests.post('http://localhost:8080/api/register', json={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123'
        }, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            user_id = result.get('user_id')
            print(f"✅ Пользователь зарегистрирован: {user_id}")
            return user_id
        else:
            print(f"⚠️ Пользователь уже существует (это нормально)")
            # Пробуем войти
            login_response = requests.post('http://localhost:8080/api/login', json={
                'username': 'testuser',
                'password': 'password123'
            }, timeout=10)
            
            if login_response.status_code == 200:
                result = login_response.json()
                user_id = result['user_info']['user_id']
                print(f"✅ Вход выполнен: {user_id}")
                return user_id
            
    except Exception as e:
        print(f"❌ Ошибка регистрации пользователя: {e}")
    
    return "user_123456"  # Fallback ID

def main():
    """Основная функция"""
    print("🌐 Запуск Tunnel System Demo")
    print("=" * 50)
    
    # Регистрируем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Проверяем зависимости
    try:
        import flask
        import websocket_server
        print("✅ Зависимости установлены")
    except ImportError as e:
        print(f"❌ Отсутствуют зависимости: {e}")
        print("   Установите: pip install -r tunnel_system/requirements.txt")
        return
    
    # Определяем пути
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    try:
        # 1. Запуск Tunnel Broker
        broker_proc = run_process(
            "Tunnel Broker",
            [sys.executable, "tunnel_broker.py", "--host", "localhost", "--port", "8080"],
            cwd=current_dir
        )
        
        if not broker_proc:
            print("❌ Не удалось запустить Tunnel Broker")
            return
        
        # Ждем готовности брокера
        if not wait_for_service("http://localhost:8080/health", timeout=15):
            print("❌ Tunnel Broker не готов")
            return
        
        # Регистрируем тестового пользователя
        user_id = register_test_user()
        
        # 2. Запуск Farm Client
        farm_proc = run_process(
            "Farm Client",
            [
                sys.executable, "farm_client.py",
                "--broker", "http://localhost:8080",
                "--farm-id", "demo-farm-001",
                "--owner-id", user_id,
                "--farm-name", "Демо ферма КУБ-1063"
            ],
            cwd=current_dir
        )
        
        if not farm_proc:
            print("❌ Не удалось запустить Farm Client")
            return
        
        # Даем время на регистрацию фермы
        time.sleep(5)
        
        # 3. Запуск Mobile App
        mobile_proc = run_process(
            "Mobile App",
            [
                sys.executable, "mobile_app.py",
                "--broker", "http://localhost:8080",
                "--host", "localhost",
                "--port", "5000"
            ],
            cwd=current_dir
        )
        
        if not mobile_proc:
            print("❌ Не удалось запустить Mobile App")
            return
        
        # Ждем готовности мобильного приложения
        if wait_for_service("http://localhost:5000", timeout=10):
            print("\n" + "=" * 50)
            print("🎉 Tunnel System успешно запущен!")
            print("=" * 50)
            print(f"📊 Tunnel Broker:  http://localhost:8080/health")
            print(f"📱 Mobile App:     http://localhost:5000")
            print(f"👤 Тест. логин:    testuser / password123")
            print(f"🏭 Ферма:          demo-farm-001")
            print("=" * 50)
            print("💡 Для остановки нажмите Ctrl+C")
            print()
        
        # Основной цикл - ждем сигнал остановки
        try:
            while True:
                # Проверяем, что все процессы еще живы
                for i, proc in enumerate(processes):
                    if proc.poll() is not None:
                        print(f"⚠️ Процесс {i} завершился с кодом {proc.returncode}")
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            pass
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    
    finally:
        print("\n🛑 Остановка всех сервисов...")
        stop_all_processes()
        print("✅ Все сервисы остановлены")

if __name__ == '__main__':
    main()