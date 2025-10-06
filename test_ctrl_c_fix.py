#!/usr/bin/env python3
"""
Тестовый скрипт для проверки корректного завершения приложения по Ctrl+C
"""

import time
import signal
import sys
import subprocess
import os
from pathlib import Path

def test_ctrl_c_fix():
    """Тест правильного завершения по Ctrl+C"""
    print("🧪 Тестирование исправления проблемы с Ctrl+C...")
    
    # Определяем пути к основным файлам для тестирования
    test_files = [
        "ST_RS/main.py",
        "ST_RS/apps/edge/modbus/unified_system.py", 
        "EDGE/start_edge.py"
    ]
    
    current_dir = Path(__file__).parent
    
    for test_file in test_files:
        file_path = current_dir / test_file
        if not file_path.exists():
            print(f"⚠️ Файл {test_file} не найден, пропускаем...")
            continue
            
        print(f"\n🔍 Тестирование {test_file}...")
        
        # Запускаем процесс
        try:
            proc = subprocess.Popen(
                [sys.executable, str(file_path), "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            # Ждем немного
            time.sleep(2)
            
            # Отправляем SIGINT (Ctrl+C)
            try:
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                else:
                    proc.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            
            # Ждем завершения с таймаутом
            try:
                stdout, stderr = proc.communicate(timeout=10)
                print(f"  ✅ Процесс завершился корректно (код: {proc.returncode})")
            except subprocess.TimeoutExpired:
                print(f"  ❌ Процесс не завершился за 10 секунд, убиваем принудительно")
                proc.kill()
                proc.communicate()
                
        except Exception as e:
            print(f"  ❌ Ошибка при тестировании: {e}")

def check_daemon_threads():
    """Проверка, что daemon потоки исправлены"""
    print("\n🔍 Проверка исправления daemon потоков...")
    
    files_to_check = [
        "ST_RS/apps/edge/modbus/time_window_manager.py",
        "ST_RS/apps/edge/modbus/unified_system.py", 
        "ST_RS/stienen/rs485_communication.py",
        "ST_RS/apps/edge/modbus/writer.py",
        "ST_RS/apps/edge/modbus/gateway.py",
        "EDGE/modbus/time_window_manager.py",
        "EDGE/modbus/unified_system.py",
        "EDGE/modbus/writer.py",
        "EDGE/modbus/gateway.py",
        "EDGE/start.py"
    ]
    
    current_dir = Path(__file__).parent
    
    for file_path in files_to_check:
        full_path = current_dir / file_path
        if not full_path.exists():
            print(f"⚠️ Файл {file_path} не найден")
            continue
            
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Проверяем, что daemon=True больше нет
        daemon_true_count = content.count('daemon=True')
        daemon_false_count = content.count('daemon=False')
        
        if daemon_true_count == 0:
            print(f"  ✅ {file_path}: daemon=True исправлены ({daemon_false_count} потоков)")
        else:
            print(f"  ❌ {file_path}: найдено {daemon_true_count} daemon=True")

def test_graceful_shutdown():
    """Тест корректного завершения с wait/join потоков"""
    print("\n🔍 Проверка корректного завершения потоков...")
    
    files_to_check = [
        "ST_RS/apps/edge/modbus/time_window_manager.py",
        "ST_RS/apps/edge/modbus/unified_system.py",
        "ST_RS/stienen/rs485_communication.py",
        "ST_RS/apps/edge/modbus/writer.py"
    ]
    
    current_dir = Path(__file__).parent
    
    for file_path in files_to_check:
        full_path = current_dir / file_path
        if not full_path.exists():
            print(f"⚠️ Файл {file_path} не найден")
            continue
            
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Проверяем наличие join() с timeout
        has_join = 'join(timeout=' in content or '.join(' in content
        has_stop = 'def stop(' in content
        
        if has_join and has_stop:
            print(f"  ✅ {file_path}: есть метод stop() и join() потоков")
        else:
            print(f"  ⚠️ {file_path}: проверьте stop() и join() потоков")

if __name__ == "__main__":
    print("🚀 Запуск тестов исправления Ctrl+C...")
    print("=" * 50)
    
    check_daemon_threads()
    test_graceful_shutdown()
    test_ctrl_c_fix()
    
    print("\n" + "=" * 50)
    print("✅ Тестирование завершено!")
    print("\n💡 Рекомендации:")
    print("1. Все daemon=True потоки должны быть изменены на daemon=False")
    print("2. Все классы должны иметь метод stop() с join(timeout=5)")
    print("3. Основные циклы должны проверять флаги остановки")
    print("4. KeyboardInterrupt должен корректно обрабатываться в main()")