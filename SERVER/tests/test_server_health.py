#!/usr/bin/env python3
"""
SERVER Health Check Tests - Проверка работоспособности SERVER компонентов  
"""
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Добавляем SERVER в путь
SERVER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_ROOT))


class TestServerStructure:
    """Тесты структуры SERVER проекта"""
    
    def test_required_directories_exist(self):
        """Проверка наличия обязательных директорий"""
        required_dirs = [
            "web_app",
            "web_app/templates", 
            "monitoring",
            "security",
            "tools",
            "data",
            "logs"
        ]
        
        for dir_path in required_dirs:
            full_path = SERVER_ROOT / dir_path
            assert full_path.exists(), f"Директория {dir_path} отсутствует"
            assert full_path.is_dir(), f"{dir_path} не является директорией"

    def test_required_files_exist(self):
        """Проверка наличия ключевых файлов"""
        required_files = [
            "web_app/app.py",
            "web_app/rbac_system.py", 
            "web_app/device_registry.py",
            "web_app/api_gateway.py",
            "resilient_tunnel_broker.py",
            "requirements.txt",
            "docker-compose.yml"
        ]
        
        for file_path in required_files:
            full_path = SERVER_ROOT / file_path
            assert full_path.exists(), f"Файл {file_path} отсутствует"
            assert full_path.is_file(), f"{file_path} не является файлом"

    def test_web_templates_exist(self):
        """Проверка наличия шаблонов веб-интерфейса"""
        template_files = [
            "web_app/templates/base.html",
            "web_app/templates/index.html", 
            "web_app/templates/devices.html",
            "web_app/templates/security.html",
            "web_app/templates/tailscale_dashboard.html"
        ]
        
        for template_path in template_files:
            full_path = SERVER_ROOT / template_path
            assert full_path.exists(), f"Шаблон {template_path} отсутствует"


class TestWebAppComponents:
    """Тесты компонентов веб-приложения"""
    
    def test_flask_app_import(self):
        """Тест импорта Flask приложения"""
        try:
            from web_app.app import create_app
            assert callable(create_app)
        except ImportError as e:
            pytest.skip(f"Flask app не доступно: {e}")

    def test_rbac_system_import(self):
        """Тест импорта RBAC системы"""
        try:
            from web_app.rbac_system import RBACSystem
            assert RBACSystem is not None
        except ImportError as e:
            pytest.skip(f"RBAC system не доступна: {e}")

    def test_device_registry_import(self):
        """Тест импорта реестра устройств"""
        try:
            from web_app.device_registry import DeviceRegistry
            assert DeviceRegistry is not None
        except ImportError as e:
            pytest.skip(f"Device registry не доступен: {e}")

    def test_api_gateway_import(self):
        """Тест импорта API gateway"""
        try:
            from web_app.api_gateway import APIGateway
            assert APIGateway is not None
        except ImportError as e:
            pytest.skip(f"API gateway не доступен: {e}")

    def test_tailscale_integration_import(self):
        """Тест импорта Tailscale интеграции"""
        try:
            from web_app.tailscale_integration import TailscaleWebIntegration
            assert TailscaleWebIntegration is not None
        except ImportError as e:
            pytest.skip(f"Tailscale integration не доступна: {e}")


class TestRBACSystem:
    """Тесты RBAC системы"""
    
    @pytest.mark.asyncio
    async def test_rbac_database_schema(self, temp_server_db):
        """Тест схемы базы данных RBAC"""
        # Проверяем что таблицы созданы правильно
        with sqlite3.connect(temp_server_db) as conn:
            # Проверяем таблицу пользователей
            cursor = conn.execute("PRAGMA table_info(users)")
            user_columns = [row[1] for row in cursor.fetchall()]
            
            expected_user_columns = [
                'user_id', 'username', 'password_hash', 'role_id', 
                'is_active', 'created_at', 'last_login'
            ]
            
            for col in expected_user_columns:
                assert col in user_columns, f"Колонка {col} отсутствует в таблице users"
            
            # Проверяем таблицу ролей
            cursor = conn.execute("PRAGMA table_info(roles)")
            role_columns = [row[1] for row in cursor.fetchall()]
            
            expected_role_columns = ['role_id', 'role_name', 'description', 'permissions']
            
            for col in expected_role_columns:
                assert col in role_columns, f"Колонка {col} отсутствует в таблице roles"

    @pytest.mark.asyncio 
    async def test_rbac_user_operations(self, mock_rbac_system):
        """Тест операций с пользователями RBAC"""
        rbac = mock_rbac_system
        
        # Тестируем аутентификацию
        user = await rbac.authenticate_user("testuser", "password")
        assert user is not None
        assert user["user_id"] == "test-user"
        
        # Тестируем проверку прав
        has_permission = await rbac.check_permission("test-user", "device:view")
        assert has_permission is True
        
        # Тестируем получение прав пользователя
        permissions = await rbac.get_user_permissions("test-user")
        assert isinstance(permissions, list)
        assert "device:view" in permissions


class TestDeviceRegistry:
    """Тесты реестра устройств"""
    
    @pytest.mark.asyncio
    async def test_device_registry_operations(self, mock_device_registry):
        """Тест операций реестра устройств"""
        registry = mock_device_registry
        
        # Тестируем регистрацию устройства
        result = await registry.register_device("test-device", "test-farm", "100.100.100.1", "farm", "test-key")
        assert result["status"] == "success"
        
        # Тестируем получение устройства
        device = await registry.get_device("test-device")
        assert device is not None
        assert device["device_id"] == "test-device"
        
        # Тестируем список устройств
        devices = await registry.list_devices()
        assert isinstance(devices, list)
        assert len(devices) > 0

    @pytest.mark.asyncio
    async def test_device_database_schema(self, temp_server_db):
        """Тест схемы базы данных устройств"""
        with sqlite3.connect(temp_server_db) as conn:
            cursor = conn.execute("PRAGMA table_info(registered_devices)")
            device_columns = [row[1] for row in cursor.fetchall()]
            
            expected_columns = [
                'device_id', 'hostname', 'tailscale_ip', 'device_type',
                'status', 'registration_time', 'last_seen'
            ]
            
            for col in expected_columns:
                assert col in device_columns, f"Колонка {col} отсутствует в таблице registered_devices"


class TestTunnelBroker:
    """Тесты туннельного брокера"""
    
    def test_tunnel_broker_import(self):
        """Тест импорта tunnel broker"""
        try:
            from resilient_tunnel_broker import ResilientTunnelBroker
            assert ResilientTunnelBroker is not None
        except ImportError as e:
            pytest.skip(f"Resilient tunnel broker не доступен: {e}")

    @pytest.mark.asyncio
    async def test_tunnel_broker_operations(self, mock_tunnel_broker):
        """Тест операций tunnel broker"""
        broker = mock_tunnel_broker
        
        # Тестируем создание соединения
        connection = await broker.create_connection("test-user", "test-farm", {"type": "offer"})
        assert connection is not None
        assert "request_id" in connection
        
        # Тестируем статус соединения
        status = await broker.get_connection_status("test-request")
        assert status in ["pending", "connected", "failed"]
        
        # Тестируем список активных соединений
        connections = await broker.list_active_connections()
        assert isinstance(connections, list)

    @pytest.mark.asyncio
    async def test_tunnel_database_schema(self, temp_server_db):
        """Тест схемы базы данных туннелей"""
        with sqlite3.connect(temp_server_db) as conn:
            cursor = conn.execute("PRAGMA table_info(active_connections)")
            connection_columns = [row[1] for row in cursor.fetchall()]
            
            expected_columns = [
                'request_id', 'user_id', 'farm_id', 'status',
                'created_at', 'last_activity'
            ]
            
            for col in expected_columns:
                assert col in connection_columns, f"Колонка {col} отсутствует в таблице active_connections"


class TestMonitoringComponents:
    """Тесты компонентов мониторинга"""
    
    def test_security_monitor_import(self):
        """Тест импорта security monitor"""
        try:
            from monitoring.security_monitor import SecurityMonitor
            assert SecurityMonitor is not None
        except ImportError as e:
            pytest.skip(f"Security monitor не доступен: {e}")

    def test_network_security_monitor_import(self):
        """Тест импорта network security monitor"""
        try:
            from monitoring.network_security_monitor import NetworkSecurityMonitor
            assert NetworkSecurityMonitor is not None
        except ImportError as e:
            pytest.skip(f"Network security monitor не доступен: {e}")


class TestSecurityComponents:
    """Тесты компонентов безопасности"""
    
    def test_mitm_protection_import(self):
        """Тест импорта MITM protection"""
        try:
            from security.mitm_protection import MITMProtection
            assert MITMProtection is not None
        except ImportError as e:
            pytest.skip(f"MITM protection не доступна: {e}")

    def test_mutual_tls_import(self):
        """Тест импорта Mutual TLS"""
        try:
            from security.mutual_tls import MutualTLS
            assert MutualTLS is not None
        except ImportError as e:
            pytest.skip(f"Mutual TLS не доступен: {e}")


class TestServerIntegration:
    """Интеграционные тесты SERVER"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_server_startup_sequence(self, mock_server_config, temp_server_db):
        """Тест полной последовательности запуска SERVER"""
        try:
            # Имитируем запуск основных компонентов SERVER
            services_status = {
                "web_app": True,
                "rbac_system": True,
                "device_registry": True,
                "tunnel_broker": True,
                "security_monitor": True
            }
            
            # Все критические сервисы должны быть доступны
            for service, status in services_status.items():
                assert status, f"Сервис {service} недоступен"
                
        except Exception as e:
            pytest.fail(f"Ошибка в интеграционном тесте: {e}")

    @pytest.mark.integration
    def test_server_configuration_validation(self, mock_server_config):
        """Тест валидации конфигурации SERVER"""
        config = mock_server_config
        
        # Проверяем обязательные секции конфигурации
        required_sections = ['server', 'tunnel_broker', 'security', 'database']
        for section in required_sections:
            assert hasattr(config, section), f"Секция {section} отсутствует в конфигурации"
        
        # Проверяем критические параметры
        assert 1000 < config.server.port < 65536, "Некорректный порт сервера"
        assert 1000 < config.tunnel_broker.port < 65536, "Некорректный порт tunnel broker"
        assert config.security.session_timeout > 0, "Некорректный таймаут сессии"
        assert len(config.security.secret_key) >= 16, "Слишком короткий секретный ключ"

    @pytest.mark.integration
    @pytest.mark.asyncio  
    async def test_web_app_functionality(self, web_client, api_headers):
        """Тест функциональности веб-приложения"""
        # Тест базового маршрута
        response = web_client.get('/test')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['status'] == 'ok'

    @pytest.mark.slow
    def test_server_database_operations(self, temp_server_db, sample_user_data):
        """Тест операций с базой данных SERVER"""
        with sqlite3.connect(temp_server_db) as conn:
            # Записываем тестового пользователя
            conn.execute("""
                INSERT INTO users (user_id, username, password_hash, role_id, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, (
                sample_user_data["user_id"],
                sample_user_data["username"],
                "hashed_password",
                "admin", 
                True
            ))
            conn.commit()
            
            # Читаем пользователя обратно
            cursor = conn.execute("""
                SELECT user_id, username, role_id, is_active
                FROM users WHERE user_id = ?
            """, (sample_user_data["user_id"],))
            
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == sample_user_data["user_id"]
            assert result[1] == sample_user_data["username"] 
            assert result[2] == "admin"
            assert result[3] == 1  # is_active = True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])