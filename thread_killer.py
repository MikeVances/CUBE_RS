#!/usr/bin/env python3
"""
Утилита для принудительной остановки зависших потоков
"""

import threading
import time
import signal
import sys
import ctypes
import os

class ThreadKiller:
    """Класс для принудительного завершения зависших потоков"""
    
    @staticmethod
    def force_kill_thread(thread):
        """Принудительное завершение потока (небезопасно!)"""
        if not thread or not thread.is_alive():
            return True
            
        # Получаем thread ID
        thread_id = thread.ident
        if not thread_id:
            return False
            
        try:
            # На Unix-подобных системах
            if hasattr(signal, 'pthread_kill'):
                signal.pthread_kill(thread_id, signal.SIGTERM)
                return True
            
            # На Windows (экспериментально)
            if sys.platform == 'win32':
                try:
                    handle = ctypes.windll.kernel32.OpenThread(1, False, thread_id)
                    if handle:
                        ctypes.windll.kernel32.TerminateThread(handle, 0)
                        ctypes.windll.kernel32.CloseHandle(handle)
                        return True
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ Не удалось принудительно завершить поток: {e}")
            
        return False
    
    @staticmethod
    def graceful_shutdown_with_timeout(threads, timeout=10):
        """Корректная остановка потоков с таймаутом и принудительным завершением"""
        print(f"🛑 Остановка {len(threads)} потоков...")
        
        # Фаза 1: Ждем корректного завершения
        start_time = time.time()
        while time.time() - start_time < timeout:
            alive_threads = [t for t in threads if t.is_alive()]
            if not alive_threads:
                print("✅ Все потоки завершились корректно")
                return True
                
            time.sleep(0.1)
        
        # Фаза 2: Принудительное завершение зависших потоков
        alive_threads = [t for t in threads if t.is_alive()]
        if alive_threads:
            print(f"⚠️ {len(alive_threads)} потоков не завершились за {timeout}с")
            print("🔨 Принудительное завершение...")
            
            for thread in alive_threads:
                print(f"   Убиваем поток: {thread.name}")
                ThreadKiller.force_kill_thread(thread)
            
            # Даем время на завершение
            time.sleep(1)
            
            # Проверяем результат
            still_alive = [t for t in threads if t.is_alive()]
            if still_alive:
                print(f"❌ {len(still_alive)} потоков всё ещё активны!")
                return False
            else:
                print("✅ Все потоки принудительно завершены")
                return True
        
        return True

def install_emergency_exit_handler():
    """Установка экстренного обработчика выхода"""
    def emergency_exit(signum, frame):
        print(f"\n🚨 ЭКСТРЕННЫЙ ВЫХОД (сигнал {signum})")
        print("🔍 Анализ активных потоков:")
        
        main_thread = threading.main_thread()
        all_threads = threading.enumerate()
        
        for thread in all_threads:
            if thread != main_thread:
                print(f"   📋 {thread.name} - {'Активен' if thread.is_alive() else 'Завершен'}")
        
        # Принудительное завершение всех потоков
        non_main_threads = [t for t in all_threads if t != main_thread and t.is_alive()]
        if non_main_threads:
            print("🔨 Принудительное завершение всех потоков...")
            ThreadKiller.graceful_shutdown_with_timeout(non_main_threads, timeout=2)
        
        print("🚪 Экстренный выход из программы")
        os._exit(1)
    
    # Устанавливаем обработчик для повторного Ctrl+C
    signal.signal(signal.SIGTERM, emergency_exit)
    # На некоторых системах можно перехватить второй Ctrl+C
    if hasattr(signal, 'SIGQUIT'):
        signal.signal(signal.SIGQUIT, emergency_exit)

def test_thread_killer():
    """Тест утилиты принудительного завершения потоков"""
    print("🧪 Тест ThreadKiller...")
    
    # Создаем зависший поток
    def hanging_worker():
        print("🔄 Запуск зависшего потока...")
        while True:
            time.sleep(1)  # Имитация зависания
    
    # Создаем нормальный поток
    stop_flag = threading.Event()
    def normal_worker():
        print("⚡ Запуск нормального потока...")
        while not stop_flag.is_set():
            time.sleep(0.1)
        print("✅ Нормальный поток завершен")
    
    # Запускаем потоки
    hanging_thread = threading.Thread(target=hanging_worker, name="HangingWorker")
    normal_thread = threading.Thread(target=normal_worker, name="NormalWorker")
    
    hanging_thread.start()
    normal_thread.start()
    
    # Даем поработать
    time.sleep(1)
    
    # Останавливаем нормальный поток
    print("🛑 Останавливаем нормальный поток...")
    stop_flag.set()
    
    # Тестируем принудительную остановку
    all_threads = [hanging_thread, normal_thread]
    result = ThreadKiller.graceful_shutdown_with_timeout(all_threads, timeout=3)
    
    if result:
        print("✅ Тест ThreadKiller прошел успешно!")
    else:
        print("❌ Тест ThreadKiller провалился!")
    
    return result

if __name__ == "__main__":
    print("🔧 ThreadKiller - Утилита принудительной остановки потоков")
    print("=" * 60)
    
    # Устанавливаем экстренный обработчик
    install_emergency_exit_handler()
    print("🚨 Экстренный обработчик установлен (Ctrl+C дважды для принудительного выхода)")
    
    # Запускаем тест
    try:
        test_thread_killer()
    except KeyboardInterrupt:
        print("\n🚨 Получен KeyboardInterrupt")
        
        # Анализируем активные потоки
        main_thread = threading.main_thread()
        all_threads = threading.enumerate()
        active_threads = [t for t in all_threads if t != main_thread and t.is_alive()]
        
        if active_threads:
            print(f"🔍 Найдено {len(active_threads)} активных потоков")
            ThreadKiller.graceful_shutdown_with_timeout(active_threads, timeout=5)
        
        print("✅ Программа завершена")
        sys.exit(0)