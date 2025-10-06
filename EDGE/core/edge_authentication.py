#!/usr/bin/env python3
"""
EDGE Device Authentication Client
Интеграция с SERVER системой аутентификации с защитой от MITM атак
"""

import os
import requests
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import time

# Импортируем MITM защиту
from .security import create_mitm_protected_client, SecurityError, setup_device_mtls

# Импортируем publishing для real-time данных
from .publishing import WebSocketServer

# from core.config import get_config  # Будет добавлено позже

logger = logging.getLogger(__name__)

@dataclass
class EDGEAuthConfig:
    """Конфигурация аутентификации EDGE устройства"""
    api_key: str
    device_id: str
    farm_id: str
    server_url: str
    heartbeat_interval: int = 60  # секунды

class EDGEAuthenticatedClient:
    """
    Клиент для аутентифицированного общения с SERVER с защитой от MITM атак
    """
    
    def __init__(self, auth_config: EDGEAuthConfig, enable_mitm_protection: bool = True):
        self.config = auth_config
        self.enable_mitm_protection = enable_mitm_protection
        self.last_heartbeat = None
        self.last_error: Optional[str] = None
        
        if enable_mitm_protection:
            # Создаем защищенный от MITM клиент
            try:
                self.secure_client = create_mitm_protected_client(self.config.server_url)
                logger.info("🔒 MITM protection enabled for EDGE client")
            except Exception as e:
                logger.warning(f"Failed to enable MITM protection: {e}")
                self.secure_client = None
                self.session = requests.Session()
        else:
            self.secure_client = None
            self.session = requests.Session()
            
        # Устанавливаем заголовки для обеих сессий
        headers = {
            'Authorization': f'Bearer {self.config.api_key}',
            'X-Device-ID': self.config.device_id,
            'X-Farm-ID': self.config.farm_id,
            'Content-Type': 'application/json',
            'User-Agent': 'EDGE-Client/1.0'
        }
        
        if self.secure_client:
            self.secure_client.session.headers.update(headers)
        else:
            self.session.headers.update(headers)
        
    def _get_session(self):
        """Получение активной сессии (защищенной или обычной)"""
        return self.secure_client.session if self.secure_client else self.session
        
    def _secure_request(self, method: str, url: str, **kwargs):
        """Выполнение защищенного HTTP запроса"""
        try:
            if self.secure_client:
                return self.secure_client.secure_request(method, url, **kwargs)
            else:
                session = self._get_session()
                return session.request(method, url, **kwargs)
        except SecurityError as e:
            logger.error(f"🚨 MITM attack detected: {e}")
            self.last_error = str(e)
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            self.last_error = str(e)
            raise

    def authenticate(self) -> bool:
        """
        Проверка действительности API ключа с защитой от MITM атак
        """
        self.last_error = None
        try:
            response = self._secure_request('GET', f'{self.config.server_url}/api/auth/validate')
            
            if response.status_code == 200:
                auth_info = response.json()
                logger.info(f"✅ Authentication successful for device {self.config.device_id}")
                logger.info(f"   Farm: {auth_info.get('farm_id', 'unknown')}")
                logger.info(f"   Permissions: {', '.join(auth_info.get('permissions', []))}")
                return True
            elif response.status_code == 401:
                logger.error("❌ Authentication failed: Invalid API key")
                self.last_error = "Invalid API key"
                return False
            else:
                logger.error(f"❌ Authentication error: {response.status_code}")
                self.last_error = f"Unexpected status code {response.status_code}"
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Connection error during authentication: {e}")
            self.last_error = str(e)
            return False
    
    def send_heartbeat(self, status: str = "online", metadata: Dict[str, Any] = None) -> bool:
        """
        Отправка heartbeat сообщения на SERVER с защитой от MITM атак
        """
        try:
            payload = {
                'device_id': self.config.device_id,
                'farm_id': self.config.farm_id,
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            response = self._secure_request(
                'POST',
                f'{self.config.server_url}/api/devices/heartbeat',
                json=payload
            )
            
            if response.status_code == 200:
                self.last_heartbeat = datetime.now()
                logger.debug(f"📡 Heartbeat sent successfully")
                return True
            else:
                logger.error(f"❌ Heartbeat failed: {response.status_code}")
                return False
                
        except SecurityError as e:
            logger.error(f"🚨 MITM attack detected during heartbeat: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Heartbeat connection error: {e}")
            return False
    
    def send_data(self, device_data: Dict[str, Any]) -> bool:
        """
        Отправка данных КУБ устройств на SERVER с защитой от MITM атак
        """
        try:
            payload = {
                'device_id': self.config.device_id,
                'farm_id': self.config.farm_id,
                'timestamp': datetime.now().isoformat(),
                'data': device_data
            }
            
            response = self._secure_request(
                'POST',
                f'{self.config.server_url}/api/devices/data',
                json=payload
            )
            
            if response.status_code == 200:
                logger.debug(f"📊 Data sent successfully")
                return True
            else:
                logger.error(f"❌ Data send failed: {response.status_code}")
                return False
                
        except SecurityError as e:
            logger.error(f"🚨 MITM attack detected during data send: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Data send connection error: {e}")
            return False
    
    def request_tunnel_connection(self, target_device_id: str) -> Optional[Dict[str, Any]]:
        """
        Запрос P2P туннеля для подключения к другому устройству
        """
        try:
            payload = {
                'source_device_id': self.config.device_id,
                'target_device_id': target_device_id,
                'connection_type': 'p2p_tunnel'
            }
            
            response = self.session.post(
                f'{self.config.server_url}/api/tunnel/request',
                json=payload
            )
            
            if response.status_code == 200:
                tunnel_info = response.json()
                logger.info(f"🔗 Tunnel connection info received for {target_device_id}")
                return tunnel_info
            else:
                logger.error(f"❌ Tunnel request failed: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Tunnel request error: {e}")
            return None


def load_auth_config_from_env() -> EDGEAuthConfig:
    """
    Загрузка конфигурации аутентификации из переменных окружения
    """
    api_key = os.getenv('EDGE_API_KEY')
    if not api_key:
        raise ValueError("EDGE_API_KEY environment variable is required")
    
    device_id = os.getenv('EDGE_DEVICE_ID')
    if not device_id:
        raise ValueError("EDGE_DEVICE_ID environment variable is required")
    
    farm_id = os.getenv('EDGE_FARM_ID')
    if not farm_id:
        raise ValueError("EDGE_FARM_ID environment variable is required")
    
    server_url = os.getenv('TUNNEL_BROKER_URL', 'https://localhost:8080')
    heartbeat_interval = int(os.getenv('HEARTBEAT_INTERVAL', '60'))
    
    return EDGEAuthConfig(
        api_key=api_key,
        device_id=device_id,
        farm_id=farm_id,
        server_url=server_url,
        heartbeat_interval=heartbeat_interval
    )


class EDGEHeartbeatService:
    """
    Сервис для периодической отправки heartbeat сообщений
    """
    
    def __init__(self, auth_client: EDGEAuthenticatedClient):
        self.client = auth_client
        self.running = False
        self._last_data_snapshot = None
    
    def start(self, data_callback=None):
        """
        Запуск heartbeat сервиса
        """
        self.running = True
        logger.info(f"🔄 Starting heartbeat service (interval: {self.client.config.heartbeat_interval}s)")
        
        while self.running:
            try:
                # Получаем текущие данные если есть callback
                metadata = {}
                if data_callback:
                    try:
                        current_data = data_callback()
                        if current_data:
                            metadata = {
                                'devices_count': len(current_data.get('devices', {})),
                                'last_update': current_data.get('timestamp'),
                                'status': 'active'
                            }
                    except Exception as e:
                        logger.warning(f"Data callback error: {e}")
                        metadata['status'] = 'degraded'
                
                # Отправляем heartbeat
                success = self.client.send_heartbeat('online', metadata)
                if not success:
                    logger.warning("Heartbeat failed, will retry next interval")
                
                # Ждем до следующего heartbeat
                time.sleep(self.client.config.heartbeat_interval)
                
            except KeyboardInterrupt:
                logger.info("Heartbeat service stopped by user")
                break
            except Exception as e:
                logger.error(f"Heartbeat service error: {e}")
                time.sleep(10)  # Короткая пауза при ошибке
    
    def stop(self):
        """
        Остановка heartbeat сервиса
        """
        self.running = False
        logger.info("🛑 Heartbeat service stopped")


# Пример использования
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Загружаем конфигурацию
        config = load_auth_config_from_env()
        print(f"🔐 EDGE Device Authentication Demo")
        print(f"   Device ID: {config.device_id}")
        print(f"   Farm ID: {config.farm_id}")
        print(f"   Server: {config.server_url}")
        
        # Создаем клиента
        client = EDGEAuthenticatedClient(config)
        
        # Тестируем аутентификацию
        if client.authenticate():
            print("✅ Authentication successful!")
            
            # Отправляем тестовый heartbeat
            if client.send_heartbeat('online', {'test': True}):
                print("✅ Heartbeat sent successfully!")
            
            # Отправляем тестовые данные
            test_data = {
                'kub_devices': {
                    '1': {
                        'type': 'KUB-1063',
                        'temperature': 23.5,
                        'humidity': 65.2,
                        'co2_level': 420
                    }
                }
            }
            
            if client.send_data(test_data):
                print("✅ Data sent successfully!")
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("Please set environment variables:")
        print("  export EDGE_API_KEY='your_api_key'")
        print("  export EDGE_DEVICE_ID='your_device_id'")
        print("  export EDGE_FARM_ID='your_farm_id'")
        print("  export TUNNEL_BROKER_URL='https://your-server.com:8080'")
    except Exception as e:
        print(f"❌ Error: {e}")
