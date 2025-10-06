#!/usr/bin/env python3
"""
API Gateway для предоставления данных КУБ-1063 внешним приложениям
Работает локально и предоставляет защищенный API
Ported from archive to SERVER for centralized API management
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from typing import Optional, Dict, Any

import aiohttp
import requests

# Import SERVER security components
try:
    from ..security.mitm_protection import create_secure_client
    from ..monitoring.security_monitor import SecurityMonitor
except ImportError:
    create_secure_client = None
    SecurityMonitor = None

logger = logging.getLogger(__name__)


class APIGateway:
    """Централизованный API Gateway для взаимодействия с EDGE устройствами"""

    def __init__(self, db_path: str = "api_gateway.db"):
        self.db_path = db_path
        self.edge_url = ""
        self.api_key = ""
        self.api_secret = ""
        self.session_timeout = 30
        
        # Кэш для оптимизации запросов
        self.cache = {}
        self.cache_ttl = 60  # TTL кэша в секундах
        
        # Интеграция с мониторингом безопасности
        self.security_monitor = SecurityMonitor() if SecurityMonitor else None
        
        self.init_database()
        logger.info("🌉 API Gateway инициализирован")

    def init_database(self):
        """Инициализация базы данных для логирования API"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица логов API запросов
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        method TEXT NOT NULL,
                        source_ip TEXT,
                        user_agent TEXT,
                        api_key_used TEXT,
                        response_code INTEGER,
                        response_time_ms REAL,
                        data_size_bytes INTEGER,
                        error_message TEXT
                    )
                    """
                )
                
                # Таблица конфигурации устройств
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_configs (
                        device_id TEXT PRIMARY KEY,
                        device_name TEXT,
                        edge_url TEXT NOT NULL,
                        api_endpoint TEXT,
                        auth_config TEXT,
                        last_sync TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        metadata TEXT
                    )
                    """
                )
                
                # Индексы
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp ON api_requests(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_requests_endpoint ON api_requests(endpoint)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_device_configs_active ON device_configs(is_active)")
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных API Gateway: {e}")
            raise

    def configure(self, edge_url: str, api_key: str, api_secret: str):
        """Конфигурация подключения к EDGE Gateway"""
        self.edge_url = edge_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        logger.info(f"🔗 API Gateway настроен для {edge_url}")

    def _generate_signature(self, payload: str, timestamp: str) -> str:
        """Генерация HMAC подписи для автентификации"""
        message = f"{timestamp}{payload}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"), 
            message.encode("utf-8"), 
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_cache_key(self, endpoint: str, params: dict = None) -> str:
        """Генерация ключа кэша"""
        params_str = json.dumps(params or {}, sort_keys=True)
        return f"{endpoint}:{hashlib.md5(params_str.encode()).hexdigest()}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Проверка актуальности кэша"""
        if cache_key not in self.cache:
            return False
        
        cache_entry = self.cache[cache_key]
        return (time.time() - cache_entry["timestamp"]) < self.cache_ttl

    def _log_api_request(self, endpoint: str, method: str, response_code: int, 
                        response_time: float, data_size: int = 0, error: str = None):
        """Логирование API запроса"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO api_requests (
                        timestamp, endpoint, method, source_ip, user_agent,
                        api_key_used, response_code, response_time_ms, 
                        data_size_bytes, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        time.time(),
                        endpoint,
                        method,
                        "",  # Source IP - можно добавить через Flask
                        "",  # User Agent - можно добавить через Flask
                        self.api_key[:8] + "***" if self.api_key else "unknown",
                        response_code,
                        response_time * 1000,  # Переводим в мс
                        data_size,
                        error
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка логирования API запроса: {e}")

    def make_edge_request(self, endpoint: str, method: str = "GET", 
                         data: dict = None, use_cache: bool = True) -> Optional[dict]:
        """Выполнение запроса к EDGE устройству"""
        if not self.edge_url or not self.api_key or not self.api_secret:
            logger.error("❌ API Gateway не настроен")
            return None
        
        start_time = time.time()
        cache_key = self._get_cache_key(endpoint, data) if use_cache else None
        
        # Проверяем кэш
        if cache_key and self._is_cache_valid(cache_key) and method == "GET":
            logger.debug(f"📋 Используем кэш для {endpoint}")
            return self.cache[cache_key]["data"]
        
        try:
            url = f"{self.edge_url}/{endpoint.lstrip('/')}"
            timestamp = str(int(time.time()))
            payload = json.dumps(data) if data else ""
            signature = self._generate_signature(payload, timestamp)
            
            headers = {
                "X-API-Key": self.api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature,
                "Content-Type": "application/json",
                "User-Agent": "CUBE-RS-Server/1.0"
            }
            
            # Используем защищенный клиент если доступен
            session = create_secure_client() if create_secure_client else requests.Session()
            
            if method.upper() == "GET":
                response = session.get(url, headers=headers, timeout=self.session_timeout)
            elif method.upper() == "POST":
                response = session.post(url, headers=headers, json=data, timeout=self.session_timeout)
            else:
                logger.error(f"❌ Неподдерживаемый HTTP метод: {method}")
                return None
            
            response_time = time.time() - start_time
            data_size = len(response.content) if response.content else 0
            
            if response.status_code == 200:
                result = response.json()
                
                # Сохраняем в кэш только GET запросы
                if cache_key and method == "GET":
                    self.cache[cache_key] = {
                        "data": result,
                        "timestamp": time.time()
                    }
                
                self._log_api_request(endpoint, method, 200, response_time, data_size)
                logger.debug(f"✅ Успешный запрос к {endpoint} ({response_time:.3f}s)")
                
                return result
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self._log_api_request(endpoint, method, response.status_code, response_time, error=error_msg)
                logger.error(f"❌ API запрос неудачен: {error_msg}")
                
                # Логируем в security monitor если доступен
                if self.security_monitor:
                    self.security_monitor.log_security_event(
                        "api_error", 
                        f"EDGE API error: {error_msg}",
                        severity="medium"
                    )
                
                return None
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout connecting to {url}"
            self._log_api_request(endpoint, method, 0, time.time() - start_time, error=error_msg)
            logger.error(f"❌ {error_msg}")
            return None
        except requests.exceptions.ConnectionError:
            error_msg = f"Connection error to {url}"
            self._log_api_request(endpoint, method, 0, time.time() - start_time, error=error_msg)
            logger.error(f"❌ {error_msg}")
            return None
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self._log_api_request(endpoint, method, 0, time.time() - start_time, error=error_msg)
            logger.error(f"❌ Ошибка API запроса: {e}")
            return None

    def get_current_modbus_data(self) -> Optional[dict]:
        """Получение текущих данных Modbus через EDGE Gateway"""
        return self.make_edge_request("api/data/current", use_cache=True)

    def get_device_data(self, device_id: str) -> Optional[dict]:
        """Получение данных конкретного устройства"""
        return self.make_edge_request(f"api/devices/{device_id}/data", use_cache=True)

    def get_historical_data(self, hours: int = 24) -> Optional[dict]:
        """Получение исторических данных"""
        return self.make_edge_request(f"api/data/history?hours={hours}", use_cache=False)

    def get_system_statistics(self) -> Optional[dict]:
        """Получение статистики системы"""
        return self.make_edge_request("api/system/statistics", use_cache=True)

    def send_command(self, device_id: str, command: dict) -> Optional[dict]:
        """Отправка команды на устройство"""
        return self.make_edge_request(
            f"api/devices/{device_id}/command", 
            method="POST", 
            data=command,
            use_cache=False
        )

    def write_modbus_register(self, register: int, value: int, device_id: str = None) -> Optional[dict]:
        """Запись в Modbus регистр"""
        endpoint = "api/modbus/write"
        if device_id:
            endpoint = f"api/devices/{device_id}/modbus/write"
        
        data = {
            "register": register,
            "value": value,
            "source": "web_interface"
        }
        
        return self.make_edge_request(endpoint, method="POST", data=data, use_cache=False)

    def get_device_health(self, device_id: str = None) -> Optional[dict]:
        """Получение состояния здоровья устройства"""
        endpoint = "health"
        if device_id:
            endpoint = f"api/devices/{device_id}/health"
        
        return self.make_edge_request(endpoint, use_cache=True)

    def register_device(self, device_config: dict) -> bool:
        """Регистрация нового EDGE устройства"""
        try:
            device_id = device_config.get("device_id", secrets.token_urlsafe(8))
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO device_configs (
                        device_id, device_name, edge_url, api_endpoint,
                        auth_config, last_sync, is_active, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        device_config.get("device_name", f"EDGE-{device_id}"),
                        device_config.get("edge_url", ""),
                        device_config.get("api_endpoint", "/api"),
                        json.dumps(device_config.get("auth_config", {})),
                        time.time(),
                        device_config.get("is_active", True),
                        json.dumps(device_config.get("metadata", {}))
                    )
                )
                conn.commit()
            
            logger.info(f"✅ Устройство {device_id} зарегистрировано в API Gateway")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации устройства: {e}")
            return False

    def get_registered_devices(self) -> list[dict]:
        """Получение списка зарегистрированных устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT device_id, device_name, edge_url, api_endpoint,
                           auth_config, last_sync, is_active, metadata
                    FROM device_configs WHERE is_active = 1
                    ORDER BY last_sync DESC
                    """
                )
                
                devices = []
                for row in cursor.fetchall():
                    device = {
                        "device_id": row[0],
                        "device_name": row[1],
                        "edge_url": row[2],
                        "api_endpoint": row[3],
                        "auth_config": json.loads(row[4]) if row[4] else {},
                        "last_sync": row[5],
                        "is_active": bool(row[6]),
                        "metadata": json.loads(row[7]) if row[7] else {}
                    }
                    devices.append(device)
                
                return devices
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка устройств: {e}")
            return []

    def get_api_statistics(self) -> dict:
        """Получение статистики API Gateway"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Общая статистика запросов
                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total_requests,
                        AVG(response_time_ms) as avg_response_time,
                        COUNT(CASE WHEN response_code = 200 THEN 1 END) as successful_requests,
                        COUNT(CASE WHEN response_code != 200 THEN 1 END) as failed_requests,
                        SUM(data_size_bytes) as total_data_transferred
                    FROM api_requests
                    WHERE timestamp > ?
                    """,
                    (time.time() - 24*3600,)  # Последние 24 часа
                )
                
                stats_row = cursor.fetchone()
                
                # Топ эндпоинтов
                cursor.execute(
                    """
                    SELECT endpoint, COUNT(*) as request_count, AVG(response_time_ms) as avg_time
                    FROM api_requests
                    WHERE timestamp > ?
                    GROUP BY endpoint
                    ORDER BY request_count DESC
                    LIMIT 10
                    """,
                    (time.time() - 24*3600,)
                )
                
                top_endpoints = [
                    {
                        "endpoint": row[0],
                        "request_count": row[1],
                        "avg_response_time": round(row[2], 2) if row[2] else 0
                    }
                    for row in cursor.fetchall()
                ]
                
                return {
                    "total_requests": stats_row[0] or 0,
                    "avg_response_time_ms": round(stats_row[1], 2) if stats_row[1] else 0,
                    "successful_requests": stats_row[2] or 0,
                    "failed_requests": stats_row[3] or 0,
                    "total_data_transferred_mb": round((stats_row[4] or 0) / (1024*1024), 2),
                    "success_rate": round((stats_row[2] or 0) / max(stats_row[0] or 1, 1) * 100, 1),
                    "cache_entries": len(self.cache),
                    "registered_devices": len(self.get_registered_devices()),
                    "top_endpoints": top_endpoints
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики API: {e}")
            return {}

    def clear_cache(self):
        """Очистка кэша"""
        self.cache.clear()
        logger.info("📍 Кэш API Gateway очищен")

    def health_check(self) -> dict:
        """Проверка состояния API Gateway"""
        try:
            # Проверяем соединение с EDGE
            edge_health = self.get_device_health()
            edge_status = "connected" if edge_health else "disconnected"
            
            return {
                "status": "healthy",
                "edge_connection": edge_status,
                "cache_entries": len(self.cache),
                "configured": bool(self.edge_url and self.api_key and self.api_secret),
                "registered_devices": len(self.get_registered_devices()),
                "uptime": "N/A"  # Можно добавить отслеживание uptime
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


if __name__ == "__main__":
    # Пример использования API Gateway
    import logging
    
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )
    
    # Создаем и конфигурируем API Gateway
    gateway = APIGateway("test_api_gateway.db")
    
    # Конфигурируем подключение к EDGE
    gateway.configure(
        edge_url="http://localhost:5020",
        api_key="test-api-key",
        api_secret="test-api-secret"
    )
    
    print("🌉 API Gateway сконфигурирован")
    
    # Проверка состояния
    health = gateway.health_check()
    print(f"👥 Health: {json.dumps(health, indent=2)}")
    
    # Получение текущих данных
    current_data = gateway.get_current_modbus_data()
    if current_data:
        print(f"📊 Текущие данные получены: {list(current_data.keys())}")
    else:
        print("⚠️ Не удалось получить текущие данные")
    
    # Показываем статистику
    stats = gateway.get_api_statistics()
    print(f"📊 Статистика API: {json.dumps(stats, indent=2)}")
    
    print("✅ Пример завершен")