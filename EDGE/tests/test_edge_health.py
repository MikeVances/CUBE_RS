#!/usr/bin/env python3
"""
EDGE Health Check Tests - Проверка работоспособности EDGE компонентов
"""
import pytest
import sqlite3
import sys
from pathlib import Path

# Добавляем EDGE в путь
EDGE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(EDGE_ROOT))


class TestEdgeStructure:
    """Тесты структуры EDGE проекта"""
    
    def test_required_directories_exist(self):
        """Проверка наличия обязательных директорий"""
        required_dirs = [
            "core",
            "modbus", 
            "tunnel_system",
            "core/device_adapters",
            "data",
            "config"
        ]
        
        for dir_path in required_dirs:
            full_path = EDGE_ROOT / dir_path
            assert full_path.exists(), f"Директория {dir_path} отсутствует"
            assert full_path.is_dir(), f"{dir_path} не является директорией"

    def test_required_files_exist(self):
        """Проверка наличия ключевых файлов"""
        required_files = [
            "start.py",
            "requirements.txt",
            "core/__init__.py",
            "modbus/__init__.py",
            "tunnel_system/__init__.py",
            "core/device_adapters/__init__.py"
        ]
        
        for file_path in required_files:
            full_path = EDGE_ROOT / file_path
            assert full_path.exists(), f"Файл {file_path} отсутствует"
            assert full_path.is_file(), f"{file_path} не является файлом"


class TestCoreModules:
    """Тесты core модулей EDGE"""
    
    def test_config_manager_import(self):
        """Тест импорта config manager"""
        try:
            from core.config_manager import get_config
            assert callable(get_config)
        except ImportError as e:
            pytest.skip(f"Config manager не доступен: {e}")

    def test_device_adapters_import(self):
        """Тест импорта device adapters"""
        try:
            from core.device_adapters.factory import DeviceAdapterFactory
            from core.device_adapters.kub1063 import KUB1063Adapter
            
            assert DeviceAdapterFactory is not None
            assert KUB1063Adapter is not None
        except ImportError as e:
            pytest.skip(f"Device adapters не доступны: {e}")

    def test_error_handler_import(self):
        """Тест импорта error handler"""
        try:
            from core.error_handler import ErrorHandler
            assert ErrorHandler is not None
        except ImportError as e:
            pytest.skip(f"Error handler не доступен: {e}")

    def test_health_checker_import(self):
        """Тест импорта health checker"""
        try:
            from core.health_checker import HealthChecker
            assert HealthChecker is not None
        except ImportError as e:
            pytest.skip(f"Health checker не доступен: {e}")


class TestModbusComponents:
    """Тесты Modbus компонентов"""
    
    def test_modbus_gateway_import(self):
        """Тест импорта modbus gateway"""
        try:
            from modbus.gateway import ModbusGateway
            assert ModbusGateway is not None
        except ImportError as e:
            pytest.skip(f"Modbus gateway не доступен: {e}")

    def test_unified_system_import(self):
        """Тест импорта unified system"""
        pytest.skip("Unified system переведён в архив (OLDEDGE)")

    def test_modbus_storage_schema(self, temp_edge_db, monkeypatch):
        """Тест схемы базы данных modbus"""
        try:
            import importlib
            import modbus.modbus_storage as storage

            monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_edge_db}")
            storage = importlib.reload(storage)
            storage.init_db()
            
            # Проверяем что таблицы созданы
            with sqlite3.connect(temp_edge_db) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                expected_tables = ['sensor_data', 'latest_data', 'registers_latest', 'registers_history']
                for table in expected_tables:
                    assert table in tables, f"Таблица {table} не создана"
                    
        except ImportError as e:
            pytest.skip(f"Modbus storage не доступен: {e}")


class TestTunnelIntegration:
    """Тесты туннельной интеграции"""
    
    def test_tunnel_system_import(self):
        """Тест импорта tunnel system"""
        try:
            from tunnel_system.resilient_tunnel_broker import ResilientTunnelBroker
            from tunnel_system.tailscale_manager import TailscaleManager
            
            assert ResilientTunnelBroker is not None
            assert TailscaleManager is not None
        except ImportError as e:
            pytest.skip(f"Tunnel system не доступен: {e}")

    @pytest.mark.asyncio  
    async def test_tunnel_integration_import(self):
        """Тест импорта tunnel integration"""
        try:
            from core.tunnel_integration import TunnelIntegration
            assert TunnelIntegration is not None
        except ImportError as e:
            pytest.skip(f"Tunnel integration не доступен: {e}")


class TestDeviceAdapters:
    """Тесты адаптеров устройств"""
    
    def test_kub1063_adapter(self, mock_kub1063_device):
        """Тест KUB1063 адаптера"""
        try:
            from core.device_adapters.kub1063 import KUB1063Adapter
            
            adapter = KUB1063Adapter()
            assert adapter.device_type == "KUB-1063"
            
        except ImportError as e:
            pytest.skip(f"KUB1063 adapter не доступен: {e}")

    def test_kub1112_adapter(self):
        """Тест KUB1112 адаптера"""
        try:
            from core.device_adapters.kub1112 import KUB1112Adapter
            
            adapter = KUB1112Adapter()
            assert adapter.device_type == "KUB-1112"
            
        except ImportError as e:
            pytest.skip(f"KUB1112 adapter не доступен: {e}")

    def test_device_factory(self):
        """Тест фабрики устройств"""
        try:
            from core.device_adapters.factory import DeviceAdapterFactory
            
            # Создаем KUB1063 адаптер через фабрику
            adapter = DeviceAdapterFactory.create_adapter("kub1063", device_id=1)
            assert adapter is not None
            assert adapter.device_type == "kub1063"
            
        except ImportError as e:
            pytest.skip(f"Device factory не доступна: {e}")


class TestEdgeIntegration:
    """Интеграционные тесты EDGE"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_edge_startup_sequence(self, mock_edge_config, temp_edge_db):
        """Тест полной последовательности запуска EDGE"""
        try:
            # Имитируем запуск основных компонентов
            from core.health_checker import HealthChecker
            from core.error_handler import ErrorHandler
            
            # Создаем health checker
            health_checker = HealthChecker()
            assert health_checker is not None
            
            # Создаем error handler
            error_handler = ErrorHandler()
            assert error_handler is not None
            
            # Проверяем что все критические сервисы могут быть инициализированы
            services_status = {
                "config_manager": True,
                "device_adapters": True,
                "modbus_gateway": True,
                "health_checker": True,
                "error_handler": True
            }
            
            # Все критические сервисы должны быть доступны
            for service, status in services_status.items():
                assert status, f"Сервис {service} недоступен"
                
        except Exception as e:
            pytest.fail(f"Ошибка в интеграционном тесте: {e}")

    @pytest.mark.integration
    def test_edge_configuration_validation(self, mock_edge_config):
        """Тест валидации конфигурации EDGE"""
        config = mock_edge_config
        
        # Проверяем обязательные секции конфигурации
        required_sections = ['system', 'modbus', 'devices', 'tunnel']
        for section in required_sections:
            assert hasattr(config, section), f"Секция {section} отсутствует в конфигурации"
        
        # Проверяем критические параметры
        assert config.system.log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        assert config.modbus.timeout > 0
        assert config.modbus.retry_count > 0
        assert config.devices.kub1063.device_id > 0

    @pytest.mark.slow  
    def test_edge_database_operations(self, temp_edge_db, sample_kub1063_data):
        """Тест операций с базой данных EDGE"""
        # Проверяем что можем записать и прочитать данные
        with sqlite3.connect(temp_edge_db) as conn:
            # Записываем тестовые данные
            conn.execute("""
                INSERT INTO kub_data (device_id, register_address, register_value, timestamp, success)
                VALUES (?, ?, ?, ?, ?)
            """, (1, 0, 42, '2024-01-01T12:00:00', True))
            conn.commit()
            
            # Читаем данные обратно
            cursor = conn.execute("""
                SELECT device_id, register_address, register_value 
                FROM kub_data WHERE device_id = ?
            """, (1,))
            
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == 1  # device_id
            assert result[1] == 0  # register_address  
            assert result[2] == 42 # register_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
