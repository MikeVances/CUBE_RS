#!/usr/bin/env python3
"""
Реальный тест завершения по Ctrl+C
"""

import asyncio
import signal
import threading
import time
import sys

class TestDaemonFix:
    def __init__(self):
        self.running = True
        self.threads = []
        
    def worker_loop(self, name):
        """Рабочий цикл потока"""
        print(f"🚀 Запущен поток {name}")
        while self.running:
            try:
                time.sleep(1)
                print(f"⚡ {name} работает...")
            except KeyboardInterrupt:
                print(f"⚠️ KeyboardInterrupt в потоке {name}")
                break
        print(f"✅ Поток {name} завершен")
    
    def start(self):
        """Запуск тестовых потоков"""
        print("🔄 Запуск тестовых потоков...")
        
        # Создаем потоки БЕЗ daemon=True
        for i in range(3):
            thread = threading.Thread(
                target=self.worker_loop, 
                args=(f"Worker-{i+1}",), 
                daemon=False  # ВАЖНО: НЕ daemon
            )
            thread.start()
            self.threads.append(thread)
    
    def stop(self):
        """Остановка всех потоков"""
        print("🛑 Остановка всех потоков...")
        self.running = False
        
        # Ждем завершения всех потоков
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    print(f"⚠️ Поток {thread.name} не завершился за 5 секунд")
                else:
                    print(f"✅ Поток {thread.name} завершен корректно")

async def main():
    """Главная функция"""
    test = TestDaemonFix()
    
    # Обработчик сигналов
    def signal_handler(signum, frame):
        print(f"\n🚨 Получен сигнал {signum} (Ctrl+C)")
        test.stop()
    
    # Устанавливаем обработчик
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запускаем тестовые потоки
        test.start()
        
        print("⏳ Ожидание... Нажмите Ctrl+C для завершения")
        
        # Ждем завершения
        while test.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🚨 KeyboardInterrupt в main()")
        test.stop()
    
    print("✅ Программа завершена корректно!")

if __name__ == "__main__":
    print("🧪 Тест корректного завершения по Ctrl+C")
    print("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🚨 Финальный KeyboardInterrupt")
        print("✅ Тест завершен!")
        
    sys.exit(0)