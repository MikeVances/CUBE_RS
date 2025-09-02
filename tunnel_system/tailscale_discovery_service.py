#!/usr/bin/env python3
"""
Tailscale Discovery Service - замена tunnel_broker для Tailscale mesh-сети
Обеспечивает обнаружение ферм и управление метаданными без централизованного брокера
"""

import asyncio
import json
import time
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading

from tailscale_manager import TailscaleManager, TailscaleFarm, TailscaleDevice

logger = logging.getLogger(__name__)

@dataclass
class FarmMetadata:
    """Метаданные фермы"""
    farm_id: str
    tailscale_ip: str
    hostname: str
    farm_name: str
    owner_id: str
    capabilities: List[str]
    api_port: int = 8080
    status: str = "online"
    last_heartbeat: float = 0
    created_at: float = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at == 0:
            self.created_at = time.time()

class TailscaleDiscoveryService:
    """Discovery Service для Tailscale mesh-сети"""
    
    def __init__(self, tailscale_manager: TailscaleManager, db_path: str = "discovery.db"):
        self.tailscale = tailscale_manager
        self.db_path = db_path
        self.app = Flask(__name__)
        CORS(self.app)
        
        self.init_database()
        self.setup_routes()
        
        # Запускаем фоновую синхронизацию
        self.sync_task = None
        
    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farms (
                    farm_id TEXT PRIMARY KEY,
                    tailscale_ip TEXT UNIQUE,
                    hostname TEXT,
                    farm_name TEXT,
                    owner_id TEXT,
                    capabilities TEXT,  -- JSON
                    api_port INTEGER DEFAULT 8080,
                    status TEXT DEFAULT 'online',
                    last_heartbeat REAL,
                    created_at REAL,
                    metadata TEXT       -- JSON
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE,
                    email TEXT UNIQUE,
                    created_at REAL
                )
            """)
            
            conn.commit()
            logger.info("База данных инициализирована")
    
    def setup_routes(self):
        """Настройка Flask маршрутов"""
        
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            return jsonify({
                'status': 'ok',
                'service': 'tailscale-discovery',
                'timestamp': time.time()
            })
        
        @self.app.route('/api/farms', methods=['GET'])
        def get_farms():
            """Получение списка всех ферм"""
            try:
                farms = self.get_all_farms()
                return jsonify({
                    'status': 'success',
                    'farms': [asdict(farm) for farm in farms]
                })
            except Exception as e:
                logger.error(f"Ошибка получения ферм: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/api/farms/<owner_id>', methods=['GET']) 
        def get_user_farms(owner_id):
            """Получение ферм конкретного пользователя"""
            try:
                farms = self.get_farms_by_owner(owner_id)
                return jsonify({
                    'status': 'success',
                    'farms': [asdict(farm) for farm in farms]
                })
            except Exception as e:
                logger.error(f"Ошибка получения ферм пользователя {owner_id}: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/api/farm/register', methods=['POST'])
        def register_farm():
            """Регистрация фермы"""
            try:
                data = request.get_json()
                required_fields = ['farm_id', 'tailscale_ip', 'hostname', 'owner_id']
                
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'status': 'error', 
                            'message': f'Отсутствует поле: {field}'
                        }), 400
                
                farm = FarmMetadata(
                    farm_id=data['farm_id'],
                    tailscale_ip=data['tailscale_ip'],
                    hostname=data['hostname'],
                    farm_name=data.get('farm_name', data['hostname']),
                    owner_id=data['owner_id'],
                    capabilities=data.get('capabilities', ['kub1063', 'monitoring']),
                    api_port=data.get('api_port', 8080),
                    metadata=data.get('metadata', {})
                )
                
                success = self.register_farm_metadata(farm)
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Ферма {farm.farm_id} зарегистрирована',
                        'farm_id': farm.farm_id
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Ошибка регистрации фермы'
                    }), 500
                
            except Exception as e:
                logger.error(f"Ошибка регистрации фермы: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/api/farm/heartbeat', methods=['POST'])
        def farm_heartbeat():
            """Heartbeat от фермы"""
            try:
                data = request.get_json()
                farm_id = data.get('farm_id')
                
                if not farm_id:
                    return jsonify({
                        'status': 'error',
                        'message': 'Отсутствует farm_id'
                    }), 400
                
                success = self.update_farm_heartbeat(farm_id, data)
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': 'Heartbeat обновлен'
                    })
                else:
                    return jsonify({
                        'status': 'error', 
                        'message': 'Ферма не найдена'
                    }), 404
                
            except Exception as e:
                logger.error(f"Ошибка heartbeat: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/api/farm/<farm_id>/status', methods=['GET'])
        def get_farm_status(farm_id):
            """Получение статуса фермы"""
            try:
                farm = self.get_farm_by_id(farm_id)
                if farm:
                    return jsonify({
                        'status': 'success',
                        'farm': asdict(farm)
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Ферма не найдена'
                    }), 404
                
            except Exception as e:
                logger.error(f"Ошибка получения статуса фермы {farm_id}: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/api/tailscale/sync', methods=['POST'])
        def sync_with_tailscale():
            """Принудительная синхронизация с Tailscale"""
            try:
                asyncio.create_task(self.sync_with_tailnet())
                return jsonify({
                    'status': 'success',
                    'message': 'Синхронизация запущена'
                })
            except Exception as e:
                logger.error(f"Ошибка синхронизации: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
    
    def register_farm_metadata(self, farm: FarmMetadata) -> bool:
        """Регистрация метаданных фермы в базе"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO farms 
                    (farm_id, tailscale_ip, hostname, farm_name, owner_id, 
                     capabilities, api_port, status, last_heartbeat, 
                     created_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    farm.farm_id, farm.tailscale_ip, farm.hostname, 
                    farm.farm_name, farm.owner_id, json.dumps(farm.capabilities),
                    farm.api_port, farm.status, time.time(),
                    farm.created_at, json.dumps(farm.metadata)
                ))
                conn.commit()
                
            logger.info(f"Ферма {farm.farm_id} зарегистрирована: {farm.tailscale_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка записи фермы в БД: {e}")
            return False
    
    def get_all_farms(self) -> List[FarmMetadata]:
        """Получение всех ферм из базы"""
        farms = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT farm_id, tailscale_ip, hostname, farm_name, owner_id,
                           capabilities, api_port, status, last_heartbeat,
                           created_at, metadata
                    FROM farms
                    ORDER BY farm_name
                """)
                
                for row in cursor.fetchall():
                    farm = FarmMetadata(
                        farm_id=row[0],
                        tailscale_ip=row[1], 
                        hostname=row[2],
                        farm_name=row[3],
                        owner_id=row[4],
                        capabilities=json.loads(row[5]),
                        api_port=row[6],
                        status=row[7],
                        last_heartbeat=row[8],
                        created_at=row[9],
                        metadata=json.loads(row[10])
                    )
                    farms.append(farm)
                    
        except Exception as e:
            logger.error(f"Ошибка получения ферм из БД: {e}")
            
        return farms
    
    def get_farms_by_owner(self, owner_id: str) -> List[FarmMetadata]:
        """Получение ферм конкретного пользователя"""
        farms = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT farm_id, tailscale_ip, hostname, farm_name, owner_id,
                           capabilities, api_port, status, last_heartbeat,
                           created_at, metadata
                    FROM farms
                    WHERE owner_id = ?
                    ORDER BY farm_name
                """, (owner_id,))
                
                for row in cursor.fetchall():
                    farm = FarmMetadata(
                        farm_id=row[0],
                        tailscale_ip=row[1],
                        hostname=row[2], 
                        farm_name=row[3],
                        owner_id=row[4],
                        capabilities=json.loads(row[5]),
                        api_port=row[6],
                        status=row[7],
                        last_heartbeat=row[8],
                        created_at=row[9],
                        metadata=json.loads(row[10])
                    )
                    farms.append(farm)
                    
        except Exception as e:
            logger.error(f"Ошибка получения ферм пользователя {owner_id}: {e}")
            
        return farms
    
    def get_farm_by_id(self, farm_id: str) -> Optional[FarmMetadata]:
        """Получение фермы по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT farm_id, tailscale_ip, hostname, farm_name, owner_id,
                           capabilities, api_port, status, last_heartbeat,
                           created_at, metadata
                    FROM farms
                    WHERE farm_id = ?
                """, (farm_id,))
                
                row = cursor.fetchone()
                if row:
                    return FarmMetadata(
                        farm_id=row[0],
                        tailscale_ip=row[1],
                        hostname=row[2],
                        farm_name=row[3], 
                        owner_id=row[4],
                        capabilities=json.loads(row[5]),
                        api_port=row[6],
                        status=row[7],
                        last_heartbeat=row[8],
                        created_at=row[9],
                        metadata=json.loads(row[10])
                    )
                    
        except Exception as e:
            logger.error(f"Ошибка получения фермы {farm_id}: {e}")
            
        return None
    
    def update_farm_heartbeat(self, farm_id: str, data: Dict[str, Any]) -> bool:
        """Обновление heartbeat фермы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Обновляем время heartbeat и статус
                update_data = {
                    'last_heartbeat': time.time(),
                    'status': data.get('status', 'online')
                }
                
                # Обновляем дополнительные метаданные если переданы
                if 'metadata' in data:
                    update_data['metadata'] = json.dumps(data['metadata'])
                
                conn.execute("""
                    UPDATE farms 
                    SET last_heartbeat = ?, status = ?
                    WHERE farm_id = ?
                """, (update_data['last_heartbeat'], update_data['status'], farm_id))
                
                affected = conn.total_changes
                conn.commit()
                
                return affected > 0
                
        except Exception as e:
            logger.error(f"Ошибка обновления heartbeat {farm_id}: {e}")
            return False
    
    async def sync_with_tailnet(self):
        """Синхронизация с реальным состоянием Tailscale сети"""
        try:
            logger.info("Запуск синхронизации с Tailnet...")
            
            # Получаем устройства из Tailscale
            tailscale_farms = await self.tailscale.get_farm_devices()
            
            # Получаем фермы из локальной базы
            db_farms = self.get_all_farms()
            db_farms_dict = {farm.tailscale_ip: farm for farm in db_farms}
            
            # Обновляем статус на основе данных Tailscale
            for ts_farm in tailscale_farms:
                tailscale_ip = ts_farm.device.tailscale_ip
                
                if tailscale_ip in db_farms_dict:
                    # Обновляем статус существующей фермы
                    status = 'online' if ts_farm.device.online else 'offline'
                    self.update_farm_heartbeat(
                        db_farms_dict[tailscale_ip].farm_id,
                        {'status': status}
                    )
                    logger.debug(f"Обновлен статус фермы {tailscale_ip}: {status}")
                else:
                    # Найдена новая ферма в Tailscale, но не в базе
                    logger.info(f"Найдена незарегистрированная ферма: {tailscale_ip}")
            
            # Помечаем фермы как offline если их нет в Tailscale
            tailscale_ips = {farm.device.tailscale_ip for farm in tailscale_farms}
            for db_farm in db_farms:
                if db_farm.tailscale_ip not in tailscale_ips:
                    self.update_farm_heartbeat(db_farm.farm_id, {'status': 'offline'})
                    logger.debug(f"Ферма {db_farm.tailscale_ip} помечена как offline")
            
            logger.info(f"Синхронизация завершена. Обработано {len(tailscale_farms)} ферм")
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации с Tailnet: {e}")
    
    async def start_background_sync(self, interval: int = 300):
        """Запуск фоновой синхронизации"""
        logger.info(f"Запуск фоновой синхронизации каждые {interval} секунд")
        
        while True:
            try:
                await self.sync_with_tailnet()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Ошибка в фоновой синхронизации: {e}")
                await asyncio.sleep(60)  # Retry через минуту
    
    def run(self, host: str = '0.0.0.0', port: int = 8082):
        """Запуск Discovery Service"""
        
        def run_sync_task():
            """Запуск синхронизации в отдельном потоке"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start_background_sync())
        
        # Запускаем фоновую синхронизацию
        sync_thread = threading.Thread(target=run_sync_task, daemon=True)
        sync_thread.start()
        
        logger.info(f"Запуск Discovery Service на {host}:{port}")
        self.app.run(host=host, port=port, debug=False)

# Пример использования
async def main():
    """Демонстрация Discovery Service"""
    
    # Настройки (в продакшене из конфига)
    TAILNET = "your-tailnet.ts.net"  
    API_KEY = "tskey-api-xxxxxxxxxx"
    
    async with TailscaleManager(TAILNET, API_KEY) as ts_manager:
        
        # Создаем Discovery Service
        discovery = TailscaleDiscoveryService(ts_manager)
        
        # Тест регистрации фермы
        test_farm = FarmMetadata(
            farm_id="test-farm-001",
            tailscale_ip="100.64.1.5", 
            hostname="gateway-001",
            farm_name="Тестовая ферма КУБ-1063",
            owner_id="user_123",
            capabilities=["kub1063", "monitoring", "control"],
            metadata={"location": "greenhouse-1", "sensors": 15}
        )
        
        # Регистрируем тестовую ферму
        success = discovery.register_farm_metadata(test_farm)
        print(f"Регистрация фермы: {'✅' if success else '❌'}")
        
        # Получаем все фермы
        farms = discovery.get_all_farms()
        print(f"\nВсего ферм в базе: {len(farms)}")
        for farm in farms:
            print(f"🏭 {farm.farm_name} ({farm.tailscale_ip}) - {farm.status}")
        
        # Запуск синхронизации
        print("\n🔄 Запуск синхронизации с Tailnet...")
        await discovery.sync_with_tailnet()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Для тестирования
    asyncio.run(main())
    
    # Для запуска сервиса
    # TAILNET = os.getenv('TAILNET', 'your-tailnet.ts.net')
    # API_KEY = os.getenv('TAILSCALE_API_KEY', 'tskey-api-xxx')
    # 
    # async def run_service():
    #     async with TailscaleManager(TAILNET, API_KEY) as ts:
    #         discovery = TailscaleDiscoveryService(ts)
    #         discovery.run(host='0.0.0.0', port=8082)
    # 
    # asyncio.run(run_service())