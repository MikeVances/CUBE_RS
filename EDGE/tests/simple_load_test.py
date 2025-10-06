#!/usr/bin/env python3
"""
Простое нагрузочное тестирование EDGE узла
Проверяет стабильность основных компонентов
"""

import asyncio
import logging
import sys
import time
import tempfile
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleLoadTester:
    """Простое нагрузочное тестирование"""
    
    def __init__(self):
        self.stats = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "start_time": None,
            "end_time": None,
            "errors": []
        }
    
    def test_config_loading(self, iterations: int = 100):
        """Тест загрузки конфигурации"""
        logger.info(f"🔄 Тестирование загрузки конфигурации ({iterations} итераций)")
        
        success_count = 0
        for i in range(iterations):
            try:
                from core.config_manager import get_config
                config = get_config()
                
                # Проверяем что конфигурация загрузилась
                assert hasattr(config, 'system')
                assert hasattr(config, 'rs485')
                
                success_count += 1
                self.stats["tests_passed"] += 1
                
            except Exception as e:
                self.stats["errors"].append(f"Config loading: {e}")
                self.stats["tests_failed"] += 1
            
            self.stats["tests_run"] += 1
        
        logger.info(f"✅ Config loading: {success_count}/{iterations} успешных")
        return success_count
    
    def test_security_manager(self, iterations: int = 50):
        """Тест Security Manager"""
        logger.info(f"🔄 Тестирование Security Manager ({iterations} итераций)")
        
        success_count = 0
        for i in range(iterations):
            try:
                from core.security_manager import get_security_manager
                sm = get_security_manager()
                
                # Простые операции
                health = sm.health_check()
                assert isinstance(health, dict)
                
                # Тест шифрования
                test_data = {"test": f"data_{i}"}
                encrypted = sm.encrypt_data(test_data)
                decrypted = sm.decrypt_data(encrypted)
                
                assert decrypted == test_data
                
                success_count += 1
                self.stats["tests_passed"] += 1
                
            except Exception as e:
                self.stats["errors"].append(f"Security Manager: {e}")
                self.stats["tests_failed"] += 1
            
            self.stats["tests_run"] += 1
        
        logger.info(f"✅ Security Manager: {success_count}/{iterations} успешных")
        return success_count
    
    def test_device_types(self, iterations: int = 50):
        """Тест типов устройств"""
        logger.info(f"🔄 Тестирование типов устройств ({iterations} итераций)")
        
        success_count = 0
        for i in range(iterations):
            try:
                from core.types import DeviceInfo, DeviceStatus, VariableInfo
                
                # Создаем тестовые объекты
                device_info = DeviceInfo(
                    device_id=f"test-{i}",
                    device_type="kub1063",
                    hostname="test-host"
                )
                
                status = DeviceStatus(
                    device_id=f"test-{i}",
                    status="connected",
                    last_seen=time.time()
                )
                
                variable = VariableInfo(
                    name="temperature",
                    address=0x00D5,
                    var_type="temperature"
                )
                
                # Проверяем что объекты создались
                assert device_info.device_id == f"test-{i}"
                assert status.status == "connected"
                assert variable.name == "temperature"
                
                success_count += 1
                self.stats["tests_passed"] += 1
                
            except Exception as e:
                self.stats["errors"].append(f"Device types: {e}")
                self.stats["tests_failed"] += 1
            
            self.stats["tests_run"] += 1
        
        logger.info(f"✅ Device types: {success_count}/{iterations} успешных")
        return success_count
    
    def test_parallel_operations(self, num_threads: int = 5, operations_per_thread: int = 20):
        """Тест параллельных операций"""
        logger.info(f"🔄 Тестирование параллельных операций ({num_threads}×{operations_per_thread})")
        
        def worker_thread(thread_id: int):
            results = {"success": 0, "errors": 0}
            
            for i in range(operations_per_thread):
                try:
                    # Тестируем разные компоненты
                    if i % 3 == 0:
                        from core.config_manager import get_config
                        config = get_config()
                        assert hasattr(config, 'system')
                    elif i % 3 == 1:
                        from core.security_manager import get_security_manager
                        sm = get_security_manager()
                        health = sm.health_check()
                        assert isinstance(health, dict)
                    else:
                        from core.types import DeviceInfo
                        device = DeviceInfo(
                            device_id=f"thread-{thread_id}-{i}",
                            device_type="test",
                            hostname="test"
                        )
                        assert device.device_id.startswith(f"thread-{thread_id}")
                    
                    results["success"] += 1
                    self.stats["tests_passed"] += 1
                    
                except Exception as e:
                    results["errors"] += 1
                    self.stats["errors"].append(f"Thread {thread_id}: {e}")
                    self.stats["tests_failed"] += 1
                
                self.stats["tests_run"] += 1
                
                # Небольшая пауза
                time.sleep(0.001)
            
            return results
        
        # Запускаем потоки
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
            thread_results = [future.result() for future in futures]
        
        total_success = sum(r["success"] for r in thread_results)
        total_errors = sum(r["errors"] for r in thread_results)
        
        logger.info(f"✅ Parallel operations: {total_success} успешных, {total_errors} ошибок")
        return total_success
    
    def test_memory_stress(self, iterations: int = 100):
        """Тест на утечки памяти"""
        logger.info(f"🔄 Тестирование памяти ({iterations} итераций)")
        
        try:
            import psutil
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            logger.info(f"Начальная память: {initial_memory:.1f} MB")
        except ImportError:
            logger.warning("psutil недоступен, пропускаем мониторинг памяти")
            initial_memory = None
        
        success_count = 0
        for i in range(iterations):
            try:
                # Создаем различные объекты для проверки утечек
                from core.security_manager import get_security_manager
                sm = get_security_manager()
                
                # Множественные операции шифрования
                large_data = {"data": "x" * 1000, "iteration": i}
                for j in range(5):
                    encrypted = sm.encrypt_data(large_data)
                    decrypted = sm.decrypt_data(encrypted)
                    assert decrypted == large_data
                
                # Создаем большие списки и удаляем их
                large_list = [f"item_{k}" for k in range(1000)]
                del large_list
                
                success_count += 1
                self.stats["tests_passed"] += 1
                
                # Проверяем память каждые 25 итераций
                if initial_memory and i % 25 == 0 and i > 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_growth = current_memory - initial_memory
                    if memory_growth > 50:  # Больше 50MB прироста
                        logger.warning(f"⚠️ Подозрение на утечку памяти: +{memory_growth:.1f} MB")
                
            except Exception as e:
                self.stats["errors"].append(f"Memory stress: {e}")
                self.stats["tests_failed"] += 1
            
            self.stats["tests_run"] += 1
        
        if initial_memory:
            final_memory = process.memory_info().rss / 1024 / 1024
            memory_growth = final_memory - initial_memory
            logger.info(f"✅ Memory stress: {success_count}/{iterations} успешных")
            logger.info(f"Память: {initial_memory:.1f} → {final_memory:.1f} MB (Δ{memory_growth:+.1f} MB)")
        else:
            logger.info(f"✅ Memory stress: {success_count}/{iterations} успешных")
        
        return success_count
    
    def run_all_tests(self):
        """Запуск всех тестов"""
        logger.info("🚀 Запуск простого нагрузочного тестирования EDGE")
        self.stats["start_time"] = time.time()
        
        try:
            # Тест 1: Конфигурация
            self.test_config_loading(100)
            
            # Тест 2: Security Manager
            self.test_security_manager(50)
            
            # Тест 3: Типы данных
            self.test_device_types(50)
            
            # Тест 4: Параллельные операции
            self.test_parallel_operations(5, 20)
            
            # Тест 5: Тест памяти
            self.test_memory_stress(100)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            self.stats["errors"].append(str(e))
        
        finally:
            self.stats["end_time"] = time.time()
            self.print_summary()
    
    def print_summary(self):
        """Итоговый отчет"""
        duration = self.stats["end_time"] - self.stats["start_time"]
        success_rate = (self.stats["tests_passed"] / max(self.stats["tests_run"], 1)) * 100
        
        print("\n" + "="*50)
        print("📊 ОТЧЕТ ПРОСТОГО НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
        print("="*50)
        print(f"🕐 Длительность: {duration:.1f} секунд")
        print(f"📈 Всего тестов: {self.stats['tests_run']}")
        print(f"✅ Пройдено: {self.stats['tests_passed']}")
        print(f"❌ Провалено: {self.stats['tests_failed']}")
        print(f"📊 Успешность: {success_rate:.1f}%")
        print(f"🔄 Тестов в секунду: {self.stats['tests_run']/duration:.1f}")
        
        if self.stats["errors"]:
            print(f"\n❌ Ошибки ({len(self.stats['errors'])}):")
            for i, error in enumerate(self.stats["errors"][:5]):
                print(f"  {i+1}. {error}")
            if len(self.stats["errors"]) > 5:
                print(f"  ... и еще {len(self.stats['errors'])-5} ошибок")
        
        # Оценка
        print(f"\n🎯 ОЦЕНКА:")
        if success_rate >= 95:
            print("✅ ОТЛИЧНО: Основные компоненты стабильны")
        elif success_rate >= 85:
            print("⚠️ ХОРОШО: Минимальные проблемы")
        elif success_rate >= 70:
            print("⚠️ УДОВЛЕТВОРИТЕЛЬНО: Нужна оптимизация")
        else:
            print("❌ ПЛОХО: Серьезные проблемы стабильности")
        
        print("="*50)

def main():
    """Главная функция"""
    tester = SimpleLoadTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()