#!/usr/bin/env python3
"""
Диагностический скрипт для анализа проблем с остановкой потоков
"""

import threading
import time
import signal
import sys
import traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor

def analyze_threads():
    """Анализ всех активных потоков"""
    print("🔍 Анализ активных потоков:")
    print("=" * 50)
    
    main_thread = threading.main_thread()
    all_threads = threading.enumerate()
    
    for thread in all_threads:
        is_main = thread == main_thread
        is_daemon = thread.daemon
        is_alive = thread.is_alive()
        
        print(f"📋 Поток: {thread.name}")
        print(f"   ID: {thread.ident}")
        print(f"   Главный: {'Да' if is_main else 'Нет'}")
        print(f"   Daemon: {'Да' if is_daemon else 'Нет'}")
        print(f"   Активен: {'Да' if is_alive else 'Нет'}")
        
        if hasattr(thread, '_target') and thread._target:
            print(f"   Функция: {thread._target}")
        
        print()

def test_blocking_operations():
    """Тест различных блокирующих операций"""
    print("🧪 Тест блокирующих операций:")
    print("=" * 50)
    
    # Тест 1: Простой цикл в потоке
    def simple_loop():
        print("🔄 Запуск простого цикла...")
        count = 0
        while count < 100:  # Ограниченный цикл
            time.sleep(0.1)
            count += 1
            if count % 10 == 0:
                print(f"   Итерация {count}")
        print("✅ Простой цикл завершен")
    
    # Тест 2: Цикл с проверкой флага
    stop_flag = threading.Event()
    
    def controlled_loop():
        print("🎛️ Запуск контролируемого цикла...")
        count = 0
        while not stop_flag.is_set():
            time.sleep(0.1)
            count += 1
            if count % 10 == 0:
                print(f"   Контролируемая итерация {count}")
            if count > 100:  # Защита от бесконечного цикла
                break
        print("✅ Контролируемый цикл завершен")
    
    # Запускаем тесты
    thread1 = threading.Thread(target=simple_loop, daemon=False)
    thread2 = threading.Thread(target=controlled_loop, daemon=False)
    
    thread1.start()
    thread2.start()
    
    # Даем время поработать
    time.sleep(2)
    
    # Останавливаем контролируемый поток
    print("🛑 Останавливаем контролируемый поток...")
    stop_flag.set()
    
    # Ждем завершения
    thread1.join(timeout=5)
    thread2.join(timeout=5)
    
    if thread1.is_alive():
        print("❌ Простой поток не завершился")
    else:
        print("✅ Простой поток завершился")
        
    if thread2.is_alive():
        print("❌ Контролируемый поток не завершился") 
    else:
        print("✅ Контролируемый поток завершился")

def test_asyncio_integration():
    """Тест интеграции с asyncio"""
    print("\n🔄 Тест интеграции с asyncio:")
    print("=" * 50)
    
    async def async_worker():
        print("⚡ Запуск async worker...")
        for i in range(10):
            await asyncio.sleep(0.1)
            print(f"   Async итерация {i}")
        print("✅ Async worker завершен")
    
    def thread_with_asyncio():
        print("🧵 Запуск потока с asyncio...")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(async_worker())
            loop.close()
        except Exception as e:
            print(f"❌ Ошибка в потоке с asyncio: {e}")
        print("✅ Поток с asyncio завершен")
    
    thread = threading.Thread(target=thread_with_asyncio, daemon=False)
    thread.start()
    thread.join(timeout=5)
    
    if thread.is_alive():
        print("❌ Поток с asyncio не завершился")
    else:
        print("✅ Поток с asyncio завершился")

def test_signal_handling():
    """Тест обработки сигналов"""
    print("\n📡 Тест обработки сигналов:")
    print("=" * 50)
    
    interrupted = threading.Event()
    
    def signal_handler(signum, frame):
        print(f"🚨 Получен сигнал {signum}")
        interrupted.set()
    
    def worker_with_signal():
        print("🔄 Запуск worker с обработкой сигналов...")
        count = 0
        while not interrupted.is_set() and count < 50:
            time.sleep(0.1)
            count += 1
            if count % 10 == 0:
                print(f"   Signal worker итерация {count}")
        print("✅ Worker с сигналами завершен")
    
    # Устанавливаем обработчик
    original_handler = signal.signal(signal.SIGINT, signal_handler)
    
    thread = threading.Thread(target=worker_with_signal, daemon=False)
    thread.start()
    
    # Симулируем сигнал через 1 секунду
    time.sleep(1)
    print("📨 Симулируем SIGINT...")
    interrupted.set()
    
    thread.join(timeout=5)
    
    # Восстанавливаем обработчик
    signal.signal(signal.SIGINT, original_handler)
    
    if thread.is_alive():
        print("❌ Worker с сигналами не завершился")
    else:
        print("✅ Worker с сигналами завершился")

def main():
    """Главная функция диагностики"""
    print("🔧 Диагностика проблем с остановкой потоков")
    print("=" * 60)
    
    # Анализ текущих потоков
    analyze_threads()
    
    # Тестирование блокирующих операций
    test_blocking_operations()
    
    # Тест asyncio
    test_asyncio_integration()
    
    # Тест сигналов
    test_signal_handling()
    
    print("\n" + "=" * 60)
    print("🏁 Диагностика завершена")
    
    # Финальный анализ потоков
    print("\n🔍 Финальный анализ потоков:")
    analyze_threads()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🚨 Получен KeyboardInterrupt в main")
        print("🔍 Анализ потоков при прерывании:")
        analyze_threads()
        print("🚪 Выход...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка в диагностике: {e}")
        traceback.print_exc()
        sys.exit(1)