#!/usr/bin/env python3
"""
Базовые тесты функциональности CUBE_RS
"""
import sys
import os
import unittest
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestBasicFunctionality(unittest.TestCase):
    """Базовые тесты системы"""
    
    def test_imports(self):
        """Тест импорта основных модулей"""
        try:
            # Проверяем импорт основных компонентов
            from modbus import gateway
            from web_app import app
            from telegram_bot import bot_main
            from tunnel_system import tunnel_broker
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")
    
    def test_config_files_exist(self):
        """Проверка наличия конфигурационных файлов"""
        config_path = project_root / "config" / "app_config.yaml"
        self.assertTrue(config_path.exists(), "app_config.yaml не найден")
        
        requirements_path = project_root / "requirements.txt"
        self.assertTrue(requirements_path.exists(), "requirements.txt не найден")
    
    def test_database_files_exist(self):
        """Проверка наличия файлов БД"""
        db_files = [
            "kub_data.db",
            "kub_commands.db", 
            "tunnel_broker.db"
        ]
        
        for db_file in db_files:
            db_path = project_root / db_file
            if not db_path.exists():
                print(f"Warning: {db_file} не найден")

class TestModbusGateway(unittest.TestCase):
    """Тесты Modbus Gateway"""
    
    def test_modbus_gateway_import(self):
        """Тест импорта Modbus Gateway"""
        try:
            from modbus.gateway import ModbusGateway
        except ImportError as e:
            self.fail(f"Failed to import ModbusGateway: {e}")

class TestWebApp(unittest.TestCase):
    """Тесты веб-приложения"""
    
    def test_flask_app_creation(self):
        """Тест создания Flask приложения"""
        try:
            from web_app.app import app
            self.assertIsNotNone(app)
        except Exception as e:
            self.fail(f"Failed to create Flask app: {e}")

class TestTelegramBot(unittest.TestCase):
    """Тесты Telegram бота"""
    
    def test_bot_import(self):
        """Тест импорта бота"""
        try:
            from telegram_bot import bot_main
        except ImportError as e:
            self.fail(f"Failed to import telegram bot: {e}")

if __name__ == '__main__':
    # Запускаем тесты
    unittest.main(verbosity=2)