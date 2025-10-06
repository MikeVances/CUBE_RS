#!/usr/bin/env python3
"""
Нагрузочное тестирование EDGE узла
Проверяет стабильность работы под нагрузкой без внешних зависимостей
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.device_registry import DeviceRegistry
    from core.health_checker import HealthChecker
    from monitoring.prometheus_config import EDGEMonitoring
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь что находитесь в директории EDGE")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EDGELoadTester:
    """Нагрузочное тестирование EDGE компонентов"""
    
    def __init__(self):
        # Создаем временную директорию для тестов
        self.temp_dir = tempfile.mkdtemp(prefix="edge_load_test_")
        os.environ["EDGE_TEST_DATA_DIR"] = self.temp_dir
        
        self.device_registry = DeviceRegistry()
        self.health_checker = HealthChecker()
        
        # Создаем мониторинг с временным файлом
        temp_metrics_file = os.path.join(self.temp_dir, "metrics.json")
        from monitoring.prometheus_config import SimpleMetrics, EDGEMonitoring
        self.monitoring = EDGEMonitoring()
        self.monitoring.metrics = SimpleMetrics(temp_metrics_file)
        
        # Статистика тестирования
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0,
            "max_response_time": 0,
            "min_response_time": float('inf'),
            "errors": [],
            "start_time": None,
            "end_time": None
        }
    
    def record_request(self, success: bool, response_time: float, error: str = None):
        """Записать результат запроса"""
        self.stats["total_requests"] += 1
        
        if success:
            self.stats["successful_requests"] += 1
        else:
            self.stats["failed_requests"] += 1
            if error:
                self.stats["errors"].append(error)
        
        # Обновляем статистику времени ответа
        if response_time > self.stats["max_response_time"]:
            self.stats["max_response_time"] = response_time
        
        if response_time < self.stats["min_response_time"]:
            self.stats["min_response_time"] = response_time
        
        # Пересчитываем среднее время
        total_time = self.stats["avg_response_time"] * (self.stats["total_requests"] - 1) + response_time
        self.stats["avg_response_time"] = total_time / self.stats["total_requests"]
    
    async def test_device_registry_load(self, iterations: int = 100):
        """Тестирование Device Registry под нагрузкой"""
        logger.info(f"🔄 Тестирование Device Registry ({iterations} итераций)")
        
        tasks = []
        for i in range(iterations):
            task = asyncio.create_task(self._device_registry_operation(i))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        logger.info(f"✅ Device Registry: {success_count} успешных, {error_count} ошибок")
        return success_count, error_count
    
    async def _device_registry_operation(self, iteration: int):
        """Операция с Device Registry"""
        start_time = time.time()
        
        try:
            # Имитируем типичные операции
            devices = self.device_registry.get_devices()
            
            if devices:
                device = devices[0]
                # Получаем данные устройства
                data = self.device_registry.get_device_data(device.device_id)
                
                # Обновляем статус
                self.device_registry.update_device_status(
                    device.device_id, 
                    "connected",
                    f"Load test iteration {iteration}"
                )
            
            response_time = time.time() - start_time
            self.record_request(True, response_time)
            
        except Exception as e:
            response_time = time.time() - start_time
            self.record_request(False, response_time, str(e))
            raise
    
    async def test_health_checker_load(self, iterations: int = 50):
        """Тестирование Health Checker под нагрузкой"""
        logger.info(f"🔄 Тестирование Health Checker ({iterations} итераций)")
        
        tasks = []
        for i in range(iterations):
            task = asyncio.create_task(self._health_check_operation())
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        logger.info(f"✅ Health Checker: {success_count} успешных, {error_count} ошибок")
        return success_count, error_count
    
    async def _health_check_operation(self):
        """Операция проверки здоровья"""
        start_time = time.time()
        
        try:
            # Проверяем системные ресурсы
            system_health = await self.health_checker.check_system_resources()
            
            # Проверяем базу данных
            db_health = await self.health_checker.check_database()
            
            # Проверяем общее состояние
            overall_health = await self.health_checker.get_overall_health()
            
            response_time = time.time() - start_time
            self.record_request(True, response_time)
            
            return {
                "system": system_health,
                "database": db_health,
                "overall": overall_health
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            self.record_request(False, response_time, str(e))
            raise
    
    def test_monitoring_load(self, iterations: int = 200):
        """Тестирование системы мониторинга под нагрузкой"""
        logger.info(f"🔄 Тестирование мониторинга ({iterations} итераций)")
        
        success_count = 0
        error_count = 0
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                # Записываем тестовые метрики
                self.monitoring.record_system_metrics(
                    cpu_percent=50 + (i % 30),
                    memory_percent=60 + (i % 20),
                    disk_percent=30 + (i % 10),
                    uptime=3600 + i
                )
                
                self.monitoring.record_device_metrics(
                    f"test-device-{i % 5}",
                    temperature=20 + (i % 15),
                    humidity=50 + (i % 30),
                    co2=400 + (i % 200),
                    response_time_ms=100 + (i % 50)
                )
                
                # Читаем dashboard данные
                dashboard = self.monitoring.get_dashboard_data()
                
                response_time = time.time() - start_time
                self.record_request(True, response_time)
                success_count += 1
                
            except Exception as e:
                response_time = time.time() - start_time
                self.record_request(False, response_time, str(e))
                error_count += 1
        
        logger.info(f"✅ Мониторинг: {success_count} успешных, {error_count} ошибок")
        return success_count, error_count
    
    def test_concurrent_operations(self, num_threads: int = 10, operations_per_thread: int = 50):
        """Тестирование одновременных операций"""
        logger.info(f"🔄 Тестирование параллельных операций ({num_threads} потоков × {operations_per_thread} операций)")
        
        def worker_thread(thread_id: int):
            """Рабочий поток"""
            results = {"success": 0, "errors": 0}
            
            for i in range(operations_per_thread):
                start_time = time.time()
                
                try:
                    # Смешанные операции
                    if i % 3 == 0:
                        # Device Registry операция
                        devices = self.device_registry.get_devices()
                    elif i % 3 == 1:
                        # Мониторинг операция
                        self.monitoring.record_system_metrics(70, 80, 40, 7200)
                    else:
                        # Алерт операция
                        self.monitoring.metrics.add_alert("INFO", f"Test alert from thread {thread_id}", "load_test")
                    
                    response_time = time.time() - start_time
                    self.record_request(True, response_time)
                    results["success"] += 1
                    
                except Exception as e:
                    response_time = time.time() - start_time
                    self.record_request(False, response_time, str(e))
                    results["errors"] += 1
                
                # Небольшая пауза между операциями
                time.sleep(0.01)
            
            return results
        
        # Запускаем потоки
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
            thread_results = [future.result() for future in futures]
        
        total_success = sum(r["success"] for r in thread_results)
        total_errors = sum(r["errors"] for r in thread_results)
        
        logger.info(f"✅ Параллельные операции: {total_success} успешных, {total_errors} ошибок")
        return total_success, total_errors
    
    def test_memory_usage(self, iterations: int = 1000):
        """Тестирование использования памяти"""
        logger.info(f"🔄 Тестирование использования памяти ({iterations} итераций)")
        
        import psutil
        process = psutil.Process()
        
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        logger.info(f"Начальное использование памяти: {initial_memory:.1f} MB")
        
        success_count = 0
        
        for i in range(iterations):
            try:
                # Создаем различные объекты
                large_dict = {f"key_{j}": f"value_{j}" * 100 for j in range(100)}
                large_list = [i] * 1000
                
                # Операции с устройствами
                self.device_registry.get_devices()
                
                # Операции с мониторингом
                self.monitoring.record_system_metrics(50, 60, 30, 3600 + i)
                
                # Очищаем переменные
                del large_dict, large_list
                
                success_count += 1
                
                # Проверяем память каждые 100 итераций
                if i % 100 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_delta = current_memory - initial_memory
                    
                    if memory_delta > 100:  # Более 100MB прироста
                        logger.warning(f"⚠️ Подозрение на утечку памяти: +{memory_delta:.1f} MB")
                
            except Exception as e:
                logger.error(f"Ошибка в итерации {i}: {e}")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_delta = final_memory - initial_memory
        
        logger.info(f"✅ Тест памяти завершен: {success_count} итераций")
        logger.info(f"Использование памяти: {initial_memory:.1f} → {final_memory:.1f} MB (Δ{memory_delta:+.1f} MB)")
        
        return success_count, memory_delta
    
    async def run_full_load_test(self):
        """Запуск полного нагрузочного тестирования"""
        logger.info("🚀 Начало полного нагрузочного тестирования EDGE")
        self.stats["start_time"] = time.time()
        
        try:
            # Инициализация компонентов
            logger.info("📋 Инициализация компонентов...")
            self.device_registry.load_devices_from_config()
            
            # Тест 1: Device Registry
            await self.test_device_registry_load(100)
            
            # Тест 2: Health Checker
            await self.test_health_checker_load(50)
            
            # Тест 3: Мониторинг
            self.test_monitoring_load(200)
            
            # Тест 4: Параллельные операции
            self.test_concurrent_operations(10, 50)
            
            # Тест 5: Использование памяти
            self.test_memory_usage(1000)
            
            # Финальная проверка стабильности
            logger.info("🔍 Финальная проверка стабильности...")
            await asyncio.sleep(5)  # Даем системе отдохнуть
            
            final_health = await self.health_checker.get_overall_health()
            logger.info(f"Финальное состояние системы: {final_health}")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в нагрузочном тестировании: {e}")
            self.stats["errors"].append(str(e))
        
        finally:
            self.stats["end_time"] = time.time()
            self.print_summary()
            
            # Очищаем временную директорию
            import shutil
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"🧹 Временная директория очищена: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось очистить временную директорию: {e}")
    
    def print_summary(self):
        """Вывод итогового отчета"""
        duration = self.stats["end_time"] - self.stats["start_time"]
        success_rate = (self.stats["successful_requests"] / max(self.stats["total_requests"], 1)) * 100
        
        print("\n" + "="*60)
        print("📊 ОТЧЕТ ПО НАГРУЗОЧНОМУ ТЕСТИРОВАНИЮ")
        print("="*60)
        print(f"🕐 Длительность: {duration:.1f} секунд")
        print(f"📈 Всего запросов: {self.stats['total_requests']}")
        print(f"✅ Успешных: {self.stats['successful_requests']}")
        print(f"❌ Ошибок: {self.stats['failed_requests']}")
        print(f"📊 Успешность: {success_rate:.1f}%")
        print(f"⏱️ Среднее время ответа: {self.stats['avg_response_time']*1000:.1f} мс")
        print(f"⏱️ Мин. время ответа: {self.stats['min_response_time']*1000:.1f} мс")
        print(f"⏱️ Макс. время ответа: {self.stats['max_response_time']*1000:.1f} мс")
        print(f"🔄 RPS: {self.stats['total_requests']/duration:.1f}")
        
        if self.stats["errors"]:
            print(f"\n❌ Ошибки ({len(self.stats['errors'])}):")
            for i, error in enumerate(self.stats["errors"][:10]):  # Показываем первые 10
                print(f"  {i+1}. {error}")
            if len(self.stats["errors"]) > 10:
                print(f"  ... и еще {len(self.stats['errors'])-10} ошибок")
        
        # Оценка результатов
        print(f"\n🎯 ОЦЕНКА РЕЗУЛЬТАТОВ:")
        if success_rate >= 95:
            print("✅ ОТЛИЧНО: Система стабильна под нагрузкой")
        elif success_rate >= 85:
            print("⚠️ ХОРОШО: Система работает с минимальными проблемами")
        elif success_rate >= 70:
            print("⚠️ УДОВЛЕТВОРИТЕЛЬНО: Система нуждается в оптимизации")
        else:
            print("❌ НЕУДОВЛЕТВОРИТЕЛЬНО: Серьезные проблемы стабильности")
        
        print("="*60)

async def main():
    """Главная функция тестирования"""
    tester = EDGELoadTester()
    await tester.run_full_load_test()

if __name__ == "__main__":
    asyncio.run(main())