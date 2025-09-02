#!/usr/bin/env python3
"""
Tailscale Farm Client - клиент фермы для работы в Tailscale mesh-сети
Заменяет WebRTC координацию на прямые соединения через Tailscale
"""

import os
import sys
import json
import time
import asyncio
import logging
import socket
import aiohttp
from typing import Dict, Any, Optional
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading

# Импорт модулей проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tailscale_manager import TailscaleManager, TailscaleFarmRegistrator

logger = logging.getLogger(__name__)

class KubDataProvider:
    """Провайдер данных КУБ-1063 (заглушка для демонстрации)"""
    
    def __init__(self):
        """В реальном проекте здесь будет подключение к modbus/gateway.py"""
        self.current_data = {
            'temperature_inside': 25.5,
            'temperature_outside': 18.2,
            'humidity': 62.3,
            'co2_level': 420,
            'ph_level': 6.8,
            'ec_level': 1.2,
            'light_intensity': 800,
            'water_level': 85,
            'timestamp': time.time()
        }
    
    def get_current_data(self) -> Dict[str, Any]:
        """Получение текущих данных КУБ-1063"""
        # В реальности здесь будет вызов вашего modbus API
        self.current_data['timestamp'] = time.time()
        
        # Небольшие случайные изменения для демонстрации
        import random
        self.current_data['temperature_inside'] += random.uniform(-0.5, 0.5)
        self.current_data['humidity'] += random.uniform(-2, 2)
        self.current_data['co2_level'] += random.randint(-10, 10)
        
        return self.current_data.copy()
    
    def get_history_data(self, hours: int = 24) -> Dict[str, Any]:
        """Получение исторических данных"""
        # Заглушка исторических данных
        history = []
        current_time = time.time()
        
        for i in range(hours):
            timestamp = current_time - (i * 3600)  # Час назад
            data_point = self.current_data.copy()
            data_point['timestamp'] = timestamp
            history.append(data_point)
        
        return {
            'period_hours': hours,
            'total_points': len(history),
            'data': history
        }
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """Получение статистики системы"""
        return {
            'uptime_hours': 156.7,
            'total_measurements': 45230,
            'last_calibration': time.time() - 86400 * 7,  # Неделю назад
            'sensors_status': {
                'temperature': 'ok',
                'humidity': 'ok', 
                'co2': 'ok',
                'ph': 'warning',  # Требует калибровки
                'ec': 'ok',
                'light': 'ok'
            },
            'storage_usage_mb': 234.5
        }

class TailscaleFarmClient:
    """Клиент фермы для Tailscale mesh-сети"""
    
    def __init__(self, 
                 discovery_service_url: str,
                 farm_config: Dict[str, Any],
                 tailscale_config: Dict[str, Any]):
        
        self.discovery_url = discovery_service_url.rstrip('/')
        self.farm_config = farm_config
        self.tailscale_config = tailscale_config
        
        # Инициализация компонентов
        self.kub_data = KubDataProvider()
        self.tailscale_manager = None
        self.farm_registrator = None
        
        # Flask API сервер
        self.app = Flask(__name__)
        CORS(self.app)
        self.setup_api_routes()
        
        # Состояние клиента
        self.is_registered = False
        self.tailscale_ip = None
        self.last_heartbeat = 0
        
    def setup_api_routes(self):
        """Настройка API маршрутов фермы"""
        
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            return jsonify({
                'status': 'ok',
                'service': 'tailscale-farm-client',
                'farm_id': self.farm_config['farm_id'],
                'tailscale_ip': self.tailscale_ip,
                'is_registered': self.is_registered,
                'timestamp': time.time()
            })
        
        @self.app.route('/api/data/current')
        def get_current_data():
            """Получение текущих данных КУБ-1063"""
            try:
                data = self.kub_data.get_current_data()
                return jsonify({
                    'status': 'success',
                    'data': data,
                    'farm_id': self.farm_config['farm_id'],
                    'source': 'kub1063'
                })
            except Exception as e:
                logger.error(f"Ошибка получения текущих данных: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/data/history')
        def get_history_data():
            """Получение исторических данных"""
            try:
                hours = int(request.args.get('hours', 24))
                if hours > 168:  # Ограничение на неделю
                    hours = 168
                
                data = self.kub_data.get_history_data(hours)
                return jsonify({
                    'status': 'success',
                    'data': data,
                    'farm_id': self.farm_config['farm_id']
                })
            except Exception as e:
                logger.error(f"Ошибка получения исторических данных: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/data/statistics')
        def get_statistics():
            """Получение статистики системы"""
            try:
                stats = self.kub_data.get_system_statistics()
                return jsonify({
                    'status': 'success',
                    'data': stats,
                    'farm_id': self.farm_config['farm_id']
                })
            except Exception as e:
                logger.error(f"Ошибка получения статистики: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/farm/info')
        def get_farm_info():
            """Получение информации о ферме"""
            return jsonify({
                'status': 'success',
                'data': {
                    'farm_id': self.farm_config['farm_id'],
                    'farm_name': self.farm_config['farm_name'],
                    'owner_id': self.farm_config['owner_id'],
                    'tailscale_ip': self.tailscale_ip,
                    'capabilities': self.farm_config.get('capabilities', []),
                    'api_port': self.farm_config.get('api_port', 8080),
                    'hostname': socket.gethostname(),
                    'is_registered': self.is_registered,
                    'last_heartbeat': self.last_heartbeat
                }
            })
        
        @self.app.route('/api/commands', methods=['POST'])
        def handle_command():
            """Обработка команд управления (пример)"""
            try:
                command_data = request.get_json()
                command = command_data.get('command')
                
                if command == 'restart_sensors':
                    # Имитация перезапуска датчиков
                    logger.info("Выполнение команды: перезапуск датчиков")
                    return jsonify({
                        'status': 'success',
                        'message': 'Датчики перезапущены',
                        'executed_at': time.time()
                    })
                
                elif command == 'calibrate_ph':
                    # Имитация калибровки pH датчика
                    logger.info("Выполнение команды: калибровка pH")
                    return jsonify({
                        'status': 'success',
                        'message': 'pH датчик откалиброван',
                        'executed_at': time.time()
                    })
                
                else:
                    return jsonify({
                        'status': 'error',
                        'message': f'Неизвестная команда: {command}'
                    }), 400
                    
            except Exception as e:
                logger.error(f"Ошибка выполнения команды: {e}")
                return jsonify({
                    'status': 'error', 
                    'message': str(e)
                }), 500
    
    async def initialize_tailscale(self):
        """Инициализация Tailscale подключения"""
        try:
            # Создаем TailscaleManager
            self.tailscale_manager = TailscaleManager(
                tailnet=self.tailscale_config['tailnet'],
                api_key=self.tailscale_config['api_key']
            )
            
            # Создаем регистратор фермы
            farm_metadata = {
                'farm_name': self.farm_config['farm_name'],
                'capabilities': self.farm_config.get('capabilities', ['kub1063']),
                'owner_id': self.farm_config['owner_id']
            }
            
            self.farm_registrator = TailscaleFarmRegistrator(
                self.tailscale_manager, 
                farm_metadata
            )
            
            # Регистрируем ферму в Tailscale
            success = await self.farm_registrator.register_farm()
            if success:
                self.tailscale_ip = self.tailscale_manager.get_local_tailscale_ip()
                logger.info(f"Tailscale инициализирован: {self.tailscale_ip}")
                return True
            else:
                logger.error("Не удалось зарегистрировать ферму в Tailscale")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка инициализации Tailscale: {e}")
            return False
    
    async def register_with_discovery_service(self):
        """Регистрация в Discovery Service"""
        try:
            registration_data = {
                'farm_id': self.farm_config['farm_id'],
                'tailscale_ip': self.tailscale_ip,
                'hostname': socket.gethostname(),
                'farm_name': self.farm_config['farm_name'],
                'owner_id': self.farm_config['owner_id'],
                'capabilities': self.farm_config.get('capabilities', ['kub1063']),
                'api_port': self.farm_config.get('api_port', 8080),
                'metadata': {
                    'kub_version': '1063',
                    'sensors': ['temp', 'humidity', 'co2', 'ph', 'ec'],
                    'location': self.farm_config.get('location', 'unknown')
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.discovery_url}/api/farm/register",
                    json=registration_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Ферма зарегистрирована в Discovery Service: {result}")
                        self.is_registered = True
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка регистрации в Discovery Service: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Ошибка подключения к Discovery Service: {e}")
            return False
    
    async def send_heartbeat(self):
        """Отправка heartbeat в Discovery Service"""
        try:
            heartbeat_data = {
                'farm_id': self.farm_config['farm_id'],
                'status': 'online',
                'metadata': {
                    'last_data_update': time.time(),
                    'sensors_status': self.kub_data.get_system_statistics()['sensors_status']
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.discovery_url}/api/farm/heartbeat",
                    json=heartbeat_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        self.last_heartbeat = time.time()
                        logger.debug(f"Heartbeat отправлен успешно")
                        return True
                    else:
                        logger.warning(f"Ошибка heartbeat: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Ошибка отправки heartbeat: {e}")
            return False
    
    async def heartbeat_loop(self, interval: int = 300):
        """Цикл отправки heartbeat"""
        logger.info(f"Запуск heartbeat цикла каждые {interval} секунд")
        
        while True:
            try:
                if self.is_registered:
                    await self.send_heartbeat()
                else:
                    logger.warning("Ферма не зарегистрирована, пропуск heartbeat")
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Ошибка в heartbeat цикле: {e}")
                await asyncio.sleep(60)
    
    def run_api_server(self, host: str = '0.0.0.0', port: int = 8080):
        """Запуск API сервера в отдельном потоке"""
        def start_server():
            logger.info(f"Запуск API сервера на {host}:{port}")
            self.app.run(host=host, port=port, debug=False, threaded=True)
        
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        return server_thread
    
    async def start(self):
        """Запуск клиента фермы"""
        logger.info(f"Запуск Tailscale Farm Client для фермы {self.farm_config['farm_id']}")
        
        try:
            # 1. Инициализация Tailscale
            logger.info("1. Инициализация Tailscale...")
            if not await self.initialize_tailscale():
                raise Exception("Не удалось инициализировать Tailscale")
            
            # 2. Запуск API сервера
            logger.info("2. Запуск API сервера...")
            api_port = self.farm_config.get('api_port', 8080)
            self.run_api_server(port=api_port)
            
            # Даем серверу время на запуск
            await asyncio.sleep(2)
            
            # 3. Регистрация в Discovery Service
            logger.info("3. Регистрация в Discovery Service...")
            registration_attempts = 3
            for attempt in range(registration_attempts):
                if await self.register_with_discovery_service():
                    break
                else:
                    if attempt < registration_attempts - 1:
                        logger.warning(f"Попытка регистрации {attempt + 1} неудачна, повтор через 10 секунд...")
                        await asyncio.sleep(10)
                    else:
                        logger.error("Все попытки регистрации исчерпаны")
                        raise Exception("Не удалось зарегистрироваться в Discovery Service")
            
            # 4. Запуск heartbeat цикла
            logger.info("4. Запуск heartbeat цикла...")
            await self.heartbeat_loop()
            
        except Exception as e:
            logger.error(f"Критическая ошибка запуска клиента: {e}")
            raise

# Конфигурация и точка входа
async def main():
    """Главная функция для запуска клиента фермы"""
    
    # Конфигурация фермы
    farm_config = {
        'farm_id': os.getenv('FARM_ID', f"farm-{socket.gethostname()}"),
        'farm_name': os.getenv('FARM_NAME', f"Ферма КУБ-1063 {socket.gethostname()}"),
        'owner_id': os.getenv('OWNER_ID', 'user_default'),
        'capabilities': ['kub1063', 'monitoring', 'control'],
        'api_port': int(os.getenv('API_PORT', '8080')),
        'location': os.getenv('FARM_LOCATION', 'greenhouse-1')
    }
    
    # Конфигурация Tailscale
    tailscale_config = {
        'tailnet': os.getenv('TAILNET', 'your-tailnet.ts.net'),
        'api_key': os.getenv('TAILSCALE_API_KEY', 'tskey-api-xxx')
    }
    
    # URL Discovery Service
    discovery_url = os.getenv('DISCOVERY_SERVICE_URL', 'http://discovery-service:8082')
    
    # Создаем и запускаем клиента
    client = TailscaleFarmClient(discovery_url, farm_config, tailscale_config)
    
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения, остановка клиента...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
    )
    
    # Запуск клиента
    asyncio.run(main())