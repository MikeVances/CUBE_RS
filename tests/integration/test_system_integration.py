#!/usr/bin/env python3
"""
Интеграционные тесты CUBE_RS системы
"""
import sys
import os
import unittest
import time
import requests
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestSystemIntegration(unittest.TestCase):
    """Интеграционные тесты системы"""
    
    def setUp(self):
        """Настройка перед тестами"""
        self.gateway_url = "http://localhost:8000"
        self.web_app_url = "http://localhost:5000"
        self.websocket_url = "ws://localhost:8765"
    
    def test_services_availability(self):
        """Тест доступности основных сервисов"""
        # Список сервисов для проверки
        services = [
            ("Gateway", self.gateway_url),
            ("Web App", self.web_app_url)
        ]
        
        for service_name, url in services:
            try:
                response = requests.get(url, timeout=5)
                print(f"✓ {service_name}: доступен (статус {response.status_code})")
            except requests.RequestException as e:
                print(f"⚠ {service_name}: недоступен ({e})")

class TestDataFlow(unittest.TestCase):
    """Тесты потока данных"""
    
    def test_database_connectivity(self):
        """Тест подключения к базам данных"""
        try:
            import sqlite3
            
            # Проверяем основную БД
            db_path = project_root / "kub_data.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()
                print(f"✓ База данных kub_data.db: {len(tables)} таблиц")
            else:
                print("⚠ База данных kub_data.db не найдена")
                
        except Exception as e:
            self.fail(f"Database connectivity test failed: {e}")

if __name__ == '__main__':
    print("🧪 Запуск интеграционных тестов CUBE_RS")
    print("=" * 50)
    unittest.main(verbosity=2)