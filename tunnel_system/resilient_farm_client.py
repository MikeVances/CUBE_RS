#!/usr/bin/env python3
"""
Resilient Farm Client - улучшенный клиент с автопереподключением
и устойчивостью к сетевым сбоям
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
import socket
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import psutil

# Добавляем пути для импорта модулей системы
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConnectionHealthMonitor:
    """Мониторинг здоровья соединений"""
    
    def __init__(self, farm_client):
        self.farm_client = farm_client
        self.connection_metrics = {}
        self.is_monitoring = False
        
    async def start_monitoring(self):
        """Запуск мониторинга"""
        self.is_monitoring = True
        logger.info("🔍 Connection Health Monitor запущен")
        
        while self.is_monitoring:
            try:
                await self.check_broker_health()
                await self.check_webrtc_connections_health()
                await self.cleanup_stale_connections()
                
                await asyncio.sleep(30)  # Проверка каждые 30 секунд
                
            except Exception as e:
                logger.error(f"Ошибка в health monitor: {e}")
                await asyncio.sleep(30)
    
    async def check_broker_health(self):
        """Проверка связи с брокером"""
        try:
            start_time = time.time()
            
            # Простой ping к брокеру
            response = requests.get(
                f"{self.farm_client.broker_url}/health",
                timeout=10
            )
            
            latency = time.time() - start_time
            
            if response.status_code == 200:
                self.connection_metrics['broker'] = {
                    'status': 'healthy',
                    'latency': latency,
                    'last_check': time.time()
                }
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Broker health check failed: {e}")
            self.connection_metrics['broker'] = {
                'status': 'unhealthy', 
                'error': str(e),
                'last_check': time.time()
            }
            
            # Инициируем переподключение к брокеру
            asyncio.create_task(self.farm_client.reconnect_to_broker())
    
    async def check_webrtc_connections_health(self):
        """Проверка здоровья WebRTC соединений"""
        current_time = time.time()
        
        for request_id, conn_info in list(self.farm_client.active_connections.items()):
            try:
                # Проверяем, не слишком ли старое соединение
                if current_time - conn_info['created_at'] > 3600:  # 1 час
                    logger.info(f"Удаляем старое соединение: {request_id}")
                    await self.farm_client.cleanup_connection(request_id)
                    continue
                
                # Пингуем соединение (если реализовано)
                if hasattr(conn_info.get('webrtc'), 'ping'):
                    await conn_info['webrtc'].ping()
                    conn_info['last_activity'] = current_time
                    
            except Exception as e:
                logger.warning(f"WebRTC соединение {request_id} неисправно: {e}")
                await self.farm_client.cleanup_connection(request_id)
    
    async def cleanup_stale_connections(self):
        """Очистка устаревших соединений"""
        current_time = time.time()
        stale_connections = []
        
        for request_id, conn_info in self.farm_client.active_connections.items():
            if current_time - conn_info.get('last_activity', 0) > 300:  # 5 минут неактивности
                stale_connections.append(request_id)
        
        for request_id in stale_connections:
            logger.info(f"Очистка неактивного соединения: {request_id}")
            await self.farm_client.cleanup_connection(request_id)

class IPChangeDetector:
    """Детектор изменения IP адреса"""
    
    def __init__(self, farm_client):
        self.farm_client = farm_client
        self.current_ip = None
        self.is_monitoring = False
        
    async def start_monitoring(self):
        """Запуск мониторинга IP"""
        self.is_monitoring = True
        self.current_ip = self.get_public_ip()
        logger.info(f"📍 IP Change Detector запущен, текущий IP: {self.current_ip}")
        
        while self.is_monitoring:
            try:
                new_ip = self.get_public_ip()
                
                if new_ip != self.current_ip:
                    logger.warning(f"🔄 IP адрес изменился: {self.current_ip} -> {new_ip}")
                    await self.handle_ip_change(self.current_ip, new_ip)
                    self.current_ip = new_ip
                
                await asyncio.sleep(60)  # Проверка каждую минуту
                
            except Exception as e:
                logger.error(f"Ошибка в IP change detector: {e}")
                await asyncio.sleep(60)
    
    def get_public_ip(self) -> str:
        """Получение публичного IP"""
        try:
            # Пробуем несколько сервисов
            services = [
                'https://ifconfig.me/ip',
                'https://icanhazip.com',
                'https://ipinfo.io/ip'
            ]
            
            for service in services:
                try:
                    response = requests.get(service, timeout=10)
                    if response.status_code == 200:
                        return response.text.strip()
                except:
                    continue
            
            # Fallback - локальный IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
                
        except Exception as e:
            logger.error(f"Не удалось определить IP: {e}")
            return "unknown"
    
    async def handle_ip_change(self, old_ip: str, new_ip: str):
        """Обработка изменения IP"""
        logger.info(f"🔄 Обработка смены IP: {old_ip} -> {new_ip}")
        
        # Немедленное обновление в брокере
        await self.farm_client.send_immediate_heartbeat()
        
        # Уведомляем активные соединения
        await self.notify_connections_about_ip_change(old_ip, new_ip)
        
        # Перезапускаем WebSocket соединение
        self.farm_client.restart_websocket()
    
    async def notify_connections_about_ip_change(self, old_ip: str, new_ip: str):
        """Уведомление активных соединений о смене IP"""
        for request_id, conn_info in list(self.farm_client.active_connections.items()):
            try:
                # Уведомляем приложение через WebRTC
                if conn_info.get('webrtc'):
                    await conn_info['webrtc'].send_notification({
                        'type': 'ip_change',
                        'old_ip': old_ip,
                        'new_ip': new_ip,
                        'action': 'reconnect_required'
                    })
            except Exception as e:
                logger.error(f"Ошибка уведомления соединения {request_id}: {e}")

class AutoReconnectManager:
    """Менеджер автоматического переподключения"""
    
    def __init__(self, farm_client):
        self.farm_client = farm_client
        self.reconnect_attempts = 0
        self.max_attempts = -1  # Бесконечно
        self.base_delay = 5  # Базовая задержка в секундах
        self.max_delay = 300  # Максимальная задержка (5 минут)
        self.is_reconnecting = False
        
    async def attempt_reconnection(self):
        """Попытка переподключения с экспоненциальной задержкой"""
        if self.is_reconnecting:
            return
        
        self.is_reconnecting = True
        
        try:
            while True:
                self.reconnect_attempts += 1
                
                # Вычисляем задержку с экспоненциальным backoff
                delay = min(self.base_delay * (2 ** min(self.reconnect_attempts - 1, 6)), self.max_delay)
                
                logger.info(f"🔄 Попытка переподключения #{self.reconnect_attempts} через {delay}с")
                
                await asyncio.sleep(delay)
                
                # Попытка переподключения к брокеру
                if await self.farm_client.connect_to_broker():
                    logger.info(f"✅ Переподключение успешно за {self.reconnect_attempts} попыток")
                    self.reconnect_attempts = 0
                    break
                else:
                    logger.warning(f"❌ Попытка переподключения #{self.reconnect_attempts} неудачна")
                    
                    # Если достигли максимума попыток
                    if self.max_attempts > 0 and self.reconnect_attempts >= self.max_attempts:
                        logger.error("🛑 Достигнут максимум попыток переподключения")
                        break
        
        finally:
            self.is_reconnecting = False
    
    def reset_attempts(self):
        """Сброс счетчика попыток при успешном соединении"""
        self.reconnect_attempts = 0

class ResilientFarmClient:
    """Улучшенный Farm Client с автопереподключением и устойчивостью"""
    
    def __init__(self, broker_url: str, farm_config: Dict):
        self.broker_url = broker_url.rstrip('/')
        self.farm_id = farm_config.get('farm_id') or f"farm_{secrets.token_hex(8)}"
        self.owner_id = farm_config.get('owner_id', 'default_user')
        self.farm_name = farm_config.get('farm_name', f"Ферма {self.farm_id}")
        self.api_port = farm_config.get('api_port', 8000)
        
        # WebSocket для уведомлений от брокера
        self.ws_url = broker_url.replace('http', 'ws').replace('https', 'wss')
        self.ws_url = f"{self.ws_url}:8081"
        self.ws = None
        
        # Активные WebRTC соединения
        self.active_connections = {}
        
        # Компоненты устойчивости
        self.health_monitor = ConnectionHealthMonitor(self)
        self.ip_detector = IPChangeDetector(self)  
        self.reconnect_manager = AutoReconnectManager(self)
        
        # Статус клиента
        self.is_running = False
        self.heartbeat_interval = 60  # 1 минута (вместо 5)
        self.is_connected_to_broker = False
        
        # Статистика
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'reconnect_count': 0,
            'ip_changes': 0,
            'uptime_start': time.time()
        }
    
    async def connect_to_broker(self) -> bool:
        """Подключение к брокеру"""
        try:
            # Регистрируем ферму
            if await self.register_farm():
                self.is_connected_to_broker = True
                self.setup_websocket()
                self.reconnect_manager.reset_attempts()
                self.stats['reconnect_count'] += 1
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Ошибка подключения к брокеру: {e}")
            return False
    
    async def reconnect_to_broker(self):
        """Переподключение к брокеру"""
        logger.info("🔄 Инициируется переподключение к брокеру...")
        self.is_connected_to_broker = False
        
        # Закрываем старое WebSocket соединение
        if self.ws:
            self.ws.close()
        
        # Запускаем процесс переподключения
        await self.reconnect_manager.attempt_reconnection()
    
    def get_local_ip(self) -> str:
        """Получение локального IP адреса"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    async def register_farm(self) -> bool:
        """Регистрация фермы в Tunnel Broker"""
        try:
            registration_data = {
                'farm_id': self.farm_id,
                'owner_id': self.owner_id,
                'farm_name': self.farm_name,
                'local_ip': self.get_local_ip(),
                'port': self.api_port,
                'api_key': secrets.token_hex(16),
                'capabilities': ['kub1063', 'monitoring', 'resilient']  # Добавляем маркер устойчивости
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/register",
                json=registration_data,
                timeout=15
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
    
    async def send_heartbeat(self) -> Dict:
        """Отправка heartbeat в Tunnel Broker"""
        try:
            heartbeat_data = {
                'farm_id': self.farm_id,
                'timestamp': time.time(),
                'status': 'online',
                'local_ip': self.get_local_ip(),
                'stats': {
                    'active_connections': len(self.active_connections),
                    'uptime': time.time() - self.stats['uptime_start'],
                    'total_connections': self.stats['total_connections']
                }
            }
            
            response = requests.post(
                f"{self.broker_url}/api/farm/heartbeat",
                json=heartbeat_data,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"Heartbeat отправлен, pending requests: {result.get('pending_requests', 0)}")
                return result
            else:
                logger.warning(f"Ошибка heartbeat: {response.status_code}")
                
                # При ошибке heartbeat инициируем переподключение
                if response.status_code in [500, 502, 503, 504]:
                    asyncio.create_task(self.reconnect_to_broker())
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Сетевая ошибка heartbeat: {e}")
            # При сетевой ошибке инициируем переподключение
            asyncio.create_task(self.reconnect_to_broker())
        except Exception as e:
            logger.error(f"Исключение при heartbeat: {e}")
        
        return {}
    
    async def send_immediate_heartbeat(self):
        """Немедленная отправка heartbeat (например, при смене IP)"""
        logger.info("📡 Отправка немедленного heartbeat...")
        result = await self.send_heartbeat()
        
        # Обрабатываем ожидающие запросы если есть
        if result.get('requests'):
            for request in result['requests']:
                asyncio.create_task(self.handle_connection_request(request))
    
    def setup_websocket(self):
        """Настройка WebSocket соединения с брокером"""
        def on_open(ws):
            logger.info("✅ WebSocket соединение с брокером установлено")
            # Регистрируем ферму в WebSocket
            ws.send(json.dumps({
                'type': 'register',
                'farm_id': self.farm_id
            }))
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                logger.info(f"📨 WebSocket сообщение: {data.get('type')}")
                
                if data.get('type') == 'connection_request':
                    # Новый запрос на соединение от мобильного приложения
                    asyncio.run_coroutine_threadsafe(
                        self.handle_connection_request(data),
                        asyncio.get_event_loop()
                    )
                    
            except Exception as e:
                logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket ошибка: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            logger.warning(f"WebSocket соединение закрыто: {close_status_code} {close_msg}")
            
            # Инициируем переподключение если мы еще активны
            if self.is_running and self.is_connected_to_broker:
                logger.info("🔄 Переподключение WebSocket через 30 секунд...")
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
    
    def restart_websocket(self):
        """Перезапуск WebSocket соединения"""
        logger.info("🔄 Перезапуск WebSocket соединения...")
        
        if self.ws:
            self.ws.close()
        
        time.sleep(2)  # Пауза перед переподключением
        self.setup_websocket()
    
    async def handle_connection_request(self, request_data: Dict):
        """Обработка запроса на P2P соединение"""
        request_id = request_data.get('request_id')
        user_id = request_data.get('user_id')
        
        logger.info(f"🔗 Обрабатываем запрос на соединение от {user_id}: {request_id}")
        
        try:
            # Получаем детали запроса от брокера
            response = requests.get(
                f"{self.broker_url}/api/connect/status/{request_id}",
                timeout=15
            )
            
            if response.status_code == 200:
                request_details = response.json()
                
                # Создаем WebRTC соединение (заглушка)
                webrtc_answer = await self.create_webrtc_answer(request_details)
                
                # Отправляем answer обратно в брокер
                answer_response = requests.post(
                    f"{self.broker_url}/api/connect/answer",
                    json={
                        'request_id': request_id,
                        'webrtc_answer': webrtc_answer
                    },
                    timeout=15
                )
                
                if answer_response.status_code == 200:
                    # Сохраняем активное соединение
                    self.active_connections[request_id] = {
                        'user_id': user_id,
                        'created_at': time.time(),
                        'last_activity': time.time(),
                        'status': 'connected',
                        'webrtc_answer': webrtc_answer
                    }
                    
                    self.stats['total_connections'] += 1
                    
                    logger.info(f"✅ WebRTC соединение установлено с {user_id}")
                else:
                    logger.error(f"Ошибка отправки answer: {answer_response.status_code}")
            else:
                logger.error(f"Ошибка получения деталей запроса: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса на соединение: {e}")
    
    async def create_webrtc_answer(self, request_details: Dict) -> Dict:
        """Создание WebRTC answer (заглушка)"""
        # В реальной реализации здесь будет aiortc
        answer = {
            "type": "answer",
            "sdp": f"v=0\r\no=- {int(time.time())} 0 IN IP4 {self.get_local_ip()}\r\ns=-\r\n..."
        }
        
        logger.info("🔗 WebRTC answer создан")
        return answer
    
    async def cleanup_connection(self, request_id: str):
        """Очистка соединения"""
        if request_id in self.active_connections:
            conn_info = self.active_connections.pop(request_id)
            logger.info(f"🧹 Очищено соединение: {request_id} (пользователь: {conn_info['user_id']})")
    
    async def heartbeat_loop(self):
        """Основной цикл heartbeat"""
        while self.is_running:
            try:
                if self.is_connected_to_broker:
                    result = await self.send_heartbeat()
                    
                    # Обрабатываем ожидающие запросы если есть
                    if result.get('requests'):
                        for request in result['requests']:
                            asyncio.create_task(self.handle_connection_request(request))
                else:
                    # Если нет соединения с брокером, пытаемся переподключиться
                    asyncio.create_task(self.reconnect_to_broker())
                
            except Exception as e:
                logger.error(f"Ошибка в heartbeat_loop: {e}")
            
            await asyncio.sleep(self.heartbeat_interval)
    
    async def start(self):
        """Запуск resilient farm client"""
        logger.info(f"🚀 Запуск Resilient Farm Client для {self.farm_name}")
        
        self.is_running = True
        
        # Подключаемся к брокеру
        if not await self.connect_to_broker():
            logger.error("❌ Не удалось подключиться к брокеру, продолжаем попытки...")
            # Не завершаем работу, а продолжаем попытки переподключения
            asyncio.create_task(self.reconnect_to_broker())
        
        # Запускаем компоненты мониторинга
        asyncio.create_task(self.health_monitor.start_monitoring())
        asyncio.create_task(self.ip_detector.start_monitoring())
        
        # Запускаем heartbeat loop
        await self.heartbeat_loop()
    
    def stop(self):
        """Остановка клиента"""
        logger.info("🛑 Остановка Resilient Farm Client")
        self.is_running = False
        
        # Останавливаем мониторинг
        self.health_monitor.is_monitoring = False
        self.ip_detector.is_monitoring = False
        
        if self.ws:
            self.ws.close()
        
        # Закрываем все активные соединения
        for request_id, conn_info in list(self.active_connections.items()):
            asyncio.create_task(self.cleanup_connection(request_id))
        
        # Выводим финальную статистику
        uptime = time.time() - self.stats['uptime_start']
        logger.info(f"📊 Статистика работы:")
        logger.info(f"   Время работы: {uptime:.1f} секунд")
        logger.info(f"   Всего соединений: {self.stats['total_connections']}")
        logger.info(f"   Переподключений: {self.stats['reconnect_count']}")
        logger.info(f"   Смен IP: {self.stats['ip_changes']}")

# Функция загрузки конфигурации (копия из оригинального файла)
def load_farm_config() -> Dict:
    """Загрузка конфигурации фермы"""
    config = {
        'farm_id': os.environ.get('FARM_ID'),
        'owner_id': os.environ.get('OWNER_ID', 'default_user'),
        'farm_name': os.environ.get('FARM_NAME', 'Resilient Ферма КУБ-1063'),
        'api_port': int(os.environ.get('API_PORT', '8000'))
    }
    
    return config

async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Resilient Farm Tunnel Client')
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
    
    # Создаем и запускаем resilient client
    client = ResilientFarmClient(args.broker, config)
    
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
        client.stop()

if __name__ == '__main__':
    asyncio.run(main())