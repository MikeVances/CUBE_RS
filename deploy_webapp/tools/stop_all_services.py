#!/usr/bin/env python3
"""
Скрипт для безопасной остановки всех сервисов системы
"""

import subprocess
import time
import signal
import sys
import os
import psutil

def find_processes_by_name(name_patterns):
    """Поиск процессов по шаблонам имен"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
            for pattern in name_patterns:
                if pattern in cmdline:
                    processes.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def stop_process_safely(proc, name, timeout=10):
    """Безопасная остановка процесса"""
    try:
        print(f"🛑 Остановка {name} (PID: {proc.pid})...")
        
        # Сначала пробуем graceful shutdown
        proc.terminate()
        
        # Ждем завершения
        try:
            proc.wait(timeout=timeout)
            print(f"✅ {name} остановлен gracefully")
            return True
        except psutil.TimeoutExpired:
            print(f"⚠️ {name} не остановился за {timeout}с, принудительно завершаем...")
            proc.kill()
            try:
                proc.wait(timeout=5)
                print(f"💀 {name} принудительно остановлен")
                return True
            except psutil.TimeoutExpired:
                print(f"❌ Не удалось остановить {name}")
                return False
                
    except psutil.NoSuchProcess:
        print(f"✅ {name} уже остановлен")
        return True
    except Exception as e:
        print(f"❌ Ошибка остановки {name}: {e}")
        return False

def main():
    print("🛑 Безопасная остановка всех сервисов системы...")
    print("=" * 50)
    
    # Список сервисов для остановки (в порядке остановки)
    services = [
        {
            "name": "MQTT Publisher",
            "patterns": ["mqtt.py", "publish/mqtt.py"]
        },
        {
            "name": "Telegram Bot", 
            "patterns": ["telegram_bot.py", "telegram_bot/bot_main.py", "telegram_bot/run_bot.py", "run_bot.py"]
        },
        {
            "name": "WebSocket Server",
            "patterns": ["websocket_server.py", "publish/websocket_server.py"]
        },
        {
            "name": "Dashboard (Streamlit)",
            "patterns": ["streamlit", "dashboard/app.py"]
        },
        {
            "name": "TCP Duplicator",
            "patterns": ["tcp_duplicator.py", "modbus/tcp_duplicator.py"]
        },
        {
            "name": "Gateway (Modbus TCP)",
            "patterns": ["gateway.py", "modbus/gateway.py", "modbus.gateway", "-m modbus.gateway"]
        }
    ]
    
    stopped_count = 0
    total_count = len(services)
    
    for service in services:
        processes = find_processes_by_name(service["patterns"])
        
        if not processes:
            print(f"ℹ️ {service['name']}: не найден")
            continue
            
        for proc in processes:
            if stop_process_safely(proc, service["name"]):
                stopped_count += 1
            time.sleep(1)  # Пауза между остановками
    
    print("=" * 50)
    print(f"📊 Результат остановки: {stopped_count}/{total_count} сервисов")
    
    # Проверяем, остались ли процессы
    remaining = []
    for service in services:
        processes = find_processes_by_name(service["patterns"])
        if processes:
            remaining.extend([f"{service['name']} (PID: {p.pid})" for p in processes])
    
    if remaining:
        print("⚠️ Оставшиеся процессы:")
        for proc in remaining:
            print(f"   - {proc}")
    else:
        print("✅ Все сервисы успешно остановлены!")
    
    print("=" * 50)

if __name__ == "__main__":
    main() 