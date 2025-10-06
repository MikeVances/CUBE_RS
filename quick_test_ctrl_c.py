#!/usr/bin/env python3
"""
Быстрый тест исправления Ctrl+C
"""

import subprocess
import time
import signal
import os
import sys

def test_ctrl_c_fix(script_path, timeout=10):
    """Тест остановки скрипта по Ctrl+C"""
    print(f"🧪 Тестирование: {script_path}")
    
    try:
        # Запускаем процесс
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )
        
        print(f"  ▶️ Процесс запущен (PID: {proc.pid})")
        
        # Ждем 3 секунды
        time.sleep(3)
        
        # Отправляем SIGINT (Ctrl+C)
        print(f"  🚨 Отправляем SIGINT...")
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            else:
                proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            print(f"  ⚠️ Процесс уже завершился")
            return True
        
        # Ждем завершения
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
            
            if exit_code == 0 or exit_code == -signal.SIGINT:
                print(f"  ✅ Завершился корректно (код: {exit_code})")
                return True
            else:
                print(f"  ⚠️ Завершился с кодом: {exit_code}")
                if stderr:
                    print(f"  ❌ Ошибки: {stderr.decode()[:200]}...")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"  ❌ НЕ ЗАВЕРШИЛСЯ за {timeout} сек - убиваем принудительно")
            proc.kill()
            proc.communicate()
            return False
            
    except Exception as e:
        print(f"  ❌ Ошибка тестирования: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 Быстрый тест исправления Ctrl+C")
    print("=" * 50)
    
    # Тестируем основные входные точки
    test_scripts = [
        "EDGE/start.py",
        "ST_RS/main.py",
        "test_real_ctrl_c.py"  # Наш тестовый скрипт
    ]
    
    results = {}
    for script in test_scripts:
        if os.path.exists(script):
            results[script] = test_ctrl_c_fix(script, timeout=15)
        else:
            print(f"⚠️ Файл {script} не найден")
            results[script] = None
    
    print("\n" + "=" * 50)
    print("📊 Результаты тестов:")
    
    for script, result in results.items():
        if result is True:
            print(f"  ✅ {script}")
        elif result is False:
            print(f"  ❌ {script}")
        else:
            print(f"  ⚠️ {script} (не найден)")
    
    # Подсчет результатов
    success = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not None)
    
    print(f"\n🎯 Итог: {success}/{total} тестов прошли успешно")
    
    if success == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Ctrl+C работает корректно!")
    else:
        print("⚠️ Есть проблемы с остановкой некоторых скриптов")

if __name__ == "__main__":
    main()