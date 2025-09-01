#!/usr/bin/env python3
"""
Farm Client - клиент для регистрации фермы в Tunnel Broker
Работает на Gateway, подключается к Tunnel Broker каждые 5 минут
"""

import os
import sys
import json
import time
import asyncio
import requests
import websocket
import threading
import secrets
import logging
from typing import Dict, Any, Optional
import socket

# Добавляем пути для импорта модулей системы
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from core.config_manager import get_config
    from core.security_manager import SecurityManager
except ImportError:
    # Fallback для тестирования
    get_config = None
    SecurityManager = None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebRTCConnection:
    """WebRTC соединение для P2P туннеля"""
    
    def __init__(self):
        # В реальной реализации здесь будет aiortc или другая WebRTC библиотека
        # Для простоты пока делаем заглушку
        self.pc = None
        self.data_channel = None
        self.is_connected = False
    
    async def create_answer(self, offer: Dict) -> Dict:
        """Создание WebRTC answer на offer от приложения"""
        # Заглушка - в реальности создается WebRTC answer
        answer = {
            "type": "answer",
            "sdp": f"v=0\r\no=- {int(time.time())} 0 IN IP4 127.0.0.1\r\ns=-\r\n..."  # Упрощенная SDP
        }
        
        logger.info("WebRTC answer создан")
        return answer
    
    async def handle_ice_candidate(self, candidate: Dict):
        """Обработка ICE кандидатов"""
        logger.info(f"ICE кандидат получен: {candidate.get('candidate', '')[:50]}...")
    
    def setup_data_channel_handlers(self):
        """Настройка обработчиков data channel"""
        if self.data_channel:
            @self.data_channel.on("open")
            def on_open():
                logger.info("WebRTC DataChannel открыт")
                self.is_connected = True
            
            @self.data_channel.on("message")
            def on_message(message):
                # Обработка сообщений от приложения через WebRTC
                self.handle_app_message(message)
    
    def handle_app_message(self, message):
        """Обработка сообщений от мобильного приложения"""
        try:
            data = json.loads(message)
            
            if data.get('type') == 'api_request':
                # Проксируем API запрос к локальному API Gateway
                response = self.proxy_api_request(data)
                self.send_to_app(response)
                
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения от приложения: {e}")
    
    def proxy_api_request(self, request_data: Dict) -> Dict:
        """Проксирование API запроса к локальному Gateway"""
        try:
            # Делаем запрос к локальному API Gateway
            url = f"http://localhost:8000{request_data.get('endpoint', '')}"
            method = request_data.get('method', 'GET')
            
            if method == 'GET':
                response = requests.get(url, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=request_data.get('data'), timeout=10)
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")
            
            return {
                'type': 'api_response',
                'request_id': request_data.get('request_id'),
                'status_code': response.status_code,
                'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            }
            
        except Exception as e:
            return {
                'type': 'api_response',
                'request_id': request_data.get('request_id'),
                'status_code': 500,
                'error': str(e)
            }
    
    def send_to_app(self, data: Dict):
        """Отправка данных в мобильное приложение"""
        if self.data_channel and self.is_connected:
            try:
                message = json.dumps(data)
                # В реальности: self.data_channel.send(message)
                logger.info(f"Отправлено в приложение: {data.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Ошибка отправки в приложение: {e}")

class FarmTunnelClient:
    """Клиент фермы для работы с Tunnel Broker"""
    
    def __init__(self, broker_url: str, farm_config: Dict):
        self.broker_url = broker_url.rstrip('/')
        self.farm_id = farm_config.get('farm_id') or f"farm_{secrets.token_hex(8)}"
        self.owner_id = farm_config.get('owner_id', 'default_user')
        self.farm_name = farm_config.get('farm_name', f"Ферма {self.farm_id}")
        self.api_port = farm_config.get('api_port', 8000)
        
        # WebSocket для уведомлений от брокера
        self.ws_url = broker_url.replace('http', 'ws').replace('https', 'wss')
        self.ws_url = f"{self.ws_url}:8081"  # WebSocket порт брокера
        self.ws = None
        
        # Активные WebRTC соединения
        self.active_connections = {}
        
        # Статус клиента
        self.is_running = False
        self.heartbeat_interval = 300  # 5 минут
    
    def get_local_ip(self) -> str:
        """Получение локального IP адреса"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    def register_farm(self) -> bool:
        """Регистрация фермы в Tunnel Broker"""
        try:
            registration_data = {
                'farm_id': self.farm_id,
                'owner_id': self.owner_id,
                'farm_name': self.farm_name,
                'local_ip': self.get_local_ip(),
                'port': self.api_port,
                'api_key': secrets.token_hex(16)
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/register",
                json=registration_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    logger.info(f"✅ Ферма {self.farm_name} зарегистрирована: {self.farm_id}")
                    return True
                else:
                    logger.error(f"Ошибка регистрации: {result.get('message')}")
            else:
                logger.error(f"HTTP ошибка регистрации: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Исключение при регистрации: {e}")
        
        return False
    
    def send_heartbeat(self) -> Dict:
        """Отправка heartbeat в Tunnel Broker"""
        try:
            heartbeat_data = {
                'farm_id': self.farm_id,
                'timestamp': time.time(),
                'status': 'online',
                'local_ip': self.get_local_ip()
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/heartbeat",
                json=heartbeat_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"Heartbeat отправлен, pending requests: {result.get('pending_requests', 0)}")
                return result
            else:
                logger.warning(f"Ошибка heartbeat: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Исключение при heartbeat: {e}")
        
        return {}
    
    def setup_websocket(self):
        """Настройка WebSocket соединения с брокером"""
        def on_open(ws):
            logger.info("WebSocket соединение с брокером установлено")
            # Регистрируем ферму в WebSocket
            ws.send(json.dumps({
                'type': 'register',
                'farm_id': self.farm_id
            }))
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                logger.info(f"Получено WebSocket сообщение: {data.get('type')}")
                
                if data.get('type') == 'connection_request':
                    # Новый запрос на соединение от мобильного приложения
                    asyncio.create_task(self.handle_connection_request(data))
                    
            except Exception as e:
                logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket ошибка: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            logger.warning("WebSocket соединение закрыто")
            # Переподключение через 30 секунд
            time.sleep(30)
            if self.is_running:
                self.setup_websocket()
        
        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Запускаем WebSocket в отдельном потоке
            ws_thread = threading.Thread(
                target=self.ws.run_forever,
                daemon=True
            )
            ws_thread.start()
            
        except Exception as e:
            logger.error(f"Ошибка настройки WebSocket: {e}")
    
    async def handle_connection_request(self, request_data: Dict):
        """Обработка запроса на P2P соединение"""
        request_id = request_data.get('request_id')
        user_id = request_data.get('user_id')
        
        logger.info(f"Обрабатываем запрос на соединение от {user_id}: {request_id}")
        
        try:
            # Получаем детали запроса от брокера
            response = requests.get(
                f"{self.broker_url}/api/connect/status/{request_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                request_details = response.json()
                
                # Создаем WebRTC соединение
                webrtc_conn = WebRTCConnection()
                
                # Создаем answer на offer от приложения
                app_offer = request_details.get('data', {}).get('app_offer', {})
                webrtc_answer = await webrtc_conn.create_answer(app_offer)
                
                # Отправляем answer обратно в брокер
                answer_response = requests.post(
                    f"{self.broker_url}/api/connect/answer",
                    json={
                        'request_id': request_id,
                        'webrtc_answer': webrtc_answer
                    },
                    timeout=10
                )
                
                if answer_response.status_code == 200:
                    # Сохраняем активное соединение
                    self.active_connections[request_id] = {
                        'webrtc': webrtc_conn,
                        'user_id': user_id,
                        'created_at': time.time()
                    }
                    
                    logger.info(f"✅ WebRTC соединение установлено с {user_id}")
                else:
                    logger.error(f"Ошибка отправки answer: {answer_response.status_code}")
            else:
                logger.error(f"Ошибка получения деталей запроса: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса на соединение: {e}")
    
    async def heartbeat_loop(self):
        """Основной цикл heartbeat"""
        while self.is_running:
            try:
                result = self.send_heartbeat()
                
                # Обрабатываем ожидающие запросы если есть
                if result.get('requests'):
                    for request in result['requests']:
                        await self.handle_connection_request(request)
                
                # Очищаем старые соединения (старше 1 часа)
                current_time = time.time()
                expired_connections = [
                    req_id for req_id, conn_info in self.active_connections.items()
                    if current_time - conn_info['created_at'] > 3600
                ]
                
                for req_id in expired_connections:
                    del self.active_connections[req_id]
                    logger.info(f"Удалено устаревшее соединение: {req_id}")
                
            except Exception as e:
                logger.error(f"Ошибка в heartbeat_loop: {e}")
            
            await asyncio.sleep(self.heartbeat_interval)
    
    async def start(self):
        """Запуск клиента фермы"""
        logger.info(f"🚀 Запуск Farm Tunnel Client для {self.farm_name}")
        
        # Регистрируем ферму
        if not self.register_farm():
            logger.error("Не удалось зарегистрировать ферму")
            return
        
        self.is_running = True
        
        # Настраиваем WebSocket соединение
        self.setup_websocket()
        
        # Запускаем heartbeat loop
        await self.heartbeat_loop()
    
    def stop(self):
        """Остановка клиента"""
        logger.info("Остановка Farm Tunnel Client")
        self.is_running = False
        
        if self.ws:
            self.ws.close()
        
        # Закрываем все активные соединения
        for conn_info in self.active_connections.values():
            try:
                # В реальности: conn_info['webrtc'].close()
                pass
            except Exception as e:
                logger.error(f"Ошибка закрытия соединения: {e}")
        
        self.active_connections.clear()

def load_farm_config() -> Dict:
    """Загрузка конфигурации фермы"""
    config = {
        'farm_id': os.environ.get('FARM_ID'),
        'owner_id': os.environ.get('OWNER_ID', 'default_user'),
        'farm_name': os.environ.get('FARM_NAME', 'Моя ферма КУБ-1063'),
        'api_port': int(os.environ.get('API_PORT', '8000'))
    }
    
    # Пытаемся загрузить из основной конфигурации
    if get_config:
        try:
            main_config = get_config()
            config.update({
                'farm_name': getattr(main_config, 'farm_name', config['farm_name']),
                'api_port': getattr(main_config.api, 'port', config['api_port']) if hasattr(main_config, 'api') else config['api_port']
            })
        except Exception as e:
            logger.warning(f"Не удалось загрузить основную конфигурацию: {e}")
    
    return config

async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Farm Tunnel Client')
    parser.add_argument('--broker', required=True, help='URL Tunnel Broker сервера')
    parser.add_argument('--farm-id', help='ID фермы')
    parser.add_argument('--owner-id', help='ID владельца фермы')
    parser.add_argument('--farm-name', help='Название фермы')
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = load_farm_config()
    
    # Переопределяем из аргументов командной строки
    if args.farm_id:
        config['farm_id'] = args.farm_id
    if args.owner_id:
        config['owner_id'] = args.owner_id
    if args.farm_name:
        config['farm_name'] = args.farm_name
    
    # Создаем и запускаем клиент
    client = FarmTunnelClient(args.broker, config)
    
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        client.stop()

if __name__ == '__main__':
    asyncio.run(main())