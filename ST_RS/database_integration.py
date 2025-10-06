#!/usr/bin/env python3
"""
PostgreSQL Database Integration for Stienen Gateway
Интеграция с базой данных PostgreSQL (совместимость с оригинальной C# системой)
"""

import asyncio
import asyncpg
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
import json

from stienen.variable_mapping import FE_Type, FE_Reference, VariableValue
from stienen.gateway_backend import DeviceInfo

@dataclass
class DatabaseConfig:
    """Конфигурация базы данных"""
    host: str = "localhost"
    port: int = 5432
    database: str = "stienen"
    username: str = "stienen" 
    password: str = "password"
    pool_min_size: int = 5
    pool_max_size: int = 20

class DatabaseManager:
    """
    Менеджер базы данных PostgreSQL
    Обеспечивает совместимость с оригинальной C# схемой БД
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self) -> bool:
        """Инициализация подключения к БД"""
        try:
            # Создаем пул соединений
            self.pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                min_size=self.config.pool_min_size,
                max_size=self.config.pool_max_size,
                command_timeout=60
            )
            
            # Проверяем подключение
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                self.logger.info(f"Подключение к PostgreSQL: {version}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка подключения к БД: {e}")
            return False
    
    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
    
    # === Управление устройствами ===
    
    async def get_gateway_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Получение гейтвея по имени"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM "Gateways" WHERE "Name" = $1',
                name
            )
            return dict(row) if row else None
    
    async def register_gateway(self, name: str, description: str = "") -> str:
        """Регистрация гейтвея в БД"""
        gateway_id = str(uuid.uuid4())
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO "Gateways" ("Id", "Name", "Descr", "Created")
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT ("Name") DO UPDATE SET
                   "Descr" = EXCLUDED."Descr", "Modified" = NOW()''',
                uuid.UUID(gateway_id), name, description, datetime.now()
            )
        
        self.logger.info(f"Гейтвей {name} зарегистрирован с ID {gateway_id}")
        return gateway_id
    
    async def register_device(self, device_info: DeviceInfo, gateway_id: str) -> bool:
        """Регистрация устройства в БД"""
        try:
            device_uuid = uuid.UUID(device_info.device_id)
            gateway_uuid = uuid.UUID(gateway_id)
            
            async with self.pool.acquire() as conn:
                # Регистрируем устройство
                await conn.execute(
                    '''INSERT INTO "Devices" 
                       ("Id", "Gid", "Address", "Module", "Name", "Descr", "Active", "Order", "FcId")
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT ("Id") DO UPDATE SET
                       "Name" = EXCLUDED."Name",
                       "Descr" = EXCLUDED."Descr",
                       "Active" = EXCLUDED."Active",
                       "FcId" = EXCLUDED."FcId"''',
                    device_uuid, gateway_uuid, device_info.address, device_info.module,
                    device_info.name, device_info.description, device_info.active,
                    device_info.address, device_info.fc_id
                )
                
                # Регистрируем версию устройства 
                await conn.execute(
                    '''INSERT INTO "VersionHists" ("Did", "Stamp", "Hardware", "Version", "VersionMinor")
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT ("Did", "Stamp") DO NOTHING''',
                    device_uuid, datetime.now(), device_info.hardware, device_info.version, 0
                )
            
            self.logger.info(f"Устройство {device_info.name} зарегистрировано в БД")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка регистрации устройства {device_info.name}: {e}")
            return False
    
    async def update_device_info(self, device_info: DeviceInfo):
        """Обновление информации об устройстве"""
        try:
            device_uuid = uuid.UUID(device_info.device_id)
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''INSERT INTO "DeviceInfoCurrent" 
                       ("Did", "TimestampChanged", "FCId", "UserNumber", "State", 
                        "AlarmOnOff", "AlarmDelayed", "AlarmRelais", "AlarmCode",
                        "AlarmControlType", "AlarmControlNr", "AlarmControlText", 
                        "AlarmExtra", "Option", "Name")
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                       ON CONFLICT ("Did") DO UPDATE SET
                       "TimestampChanged" = EXCLUDED."TimestampChanged",
                       "FCId" = EXCLUDED."FCId",
                       "UserNumber" = EXCLUDED."UserNumber", 
                       "State" = EXCLUDED."State",
                       "AlarmOnOff" = EXCLUDED."AlarmOnOff",
                       "AlarmCode" = EXCLUDED."AlarmCode",
                       "Name" = EXCLUDED."Name"''',
                    device_uuid, device_info.last_communication or datetime.now(),
                    device_info.fc_id, device_info.user_number, device_info.operation_state,
                    device_info.alarm_active, False, False, device_info.alarm_code,
                    0, 0, 0, 0, 0, device_info.name
                )
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления информации устройства: {e}")
    
    # === Управление переменными ===
    
    async def load_variable_types(self, hardware: int, version: int) -> List[FE_Type]:
        """Загрузка типов переменных из БД"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT "Hardware", "Version", "Id", "Name", "Type", "Mul", "Div", 
                          "Step", "Min", "Max", "Text", "AckChange"
                   FROM "FE_Types" 
                   WHERE "Hardware" = $1 AND "Version" = $2
                   ORDER BY "Id"''',
                hardware, version
            )
            
            types = []
            for row in rows:
                fe_type = FE_Type(
                    hardware=row['Hardware'],
                    version=row['Version'],
                    id=row['Id'],
                    name=row['Name'],
                    type=row['Type'],
                    mul=row['Mul'],
                    div=row['Div'],
                    step=row['Step'],
                    min_val=row['Min'],
                    max_val=row['Max'],
                    text=row['Text'],
                    acknowledge_change=row['AckChange']
                )
                types.append(fe_type)
            
            self.logger.info(f"Загружено {len(types)} типов переменных для HW{hardware}.{version}")
            return types
    
    async def load_variable_references(self, hardware: int, version: int) -> List[FE_Reference]:
        """Загрузка ссылок на переменные из БД"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT "Hardware", "Version", "Id", "Index", "Length", 
                          "Name", "Type", "Defop"
                   FROM "FE_References"
                   WHERE "Hardware" = $1 AND "Version" = $2
                   ORDER BY "Index"''',
                hardware, version
            )
            
            references = []
            for row in rows:
                fe_ref = FE_Reference(
                    hardware=row['Hardware'],
                    version=row['Version'],
                    id=row['Id'],
                    index=row['Index'],
                    length=row['Length'],
                    name=row['Name'],
                    type_id=row['Type'],
                    defop=row['Defop']
                )
                references.append(fe_ref)
            
            self.logger.info(f"Загружено {len(references)} ссылок на переменные для HW{hardware}.{version}")
            return references
    
    async def save_variable_types(self, types: List[FE_Type]):
        """Сохранение типов переменных в БД"""
        async with self.pool.acquire() as conn:
            for fe_type in types:
                await conn.execute(
                    '''INSERT INTO "FE_Types" 
                       ("Hardware", "Version", "Id", "Name", "Type", "Mul", "Div",
                        "Step", "Min", "Max", "Text", "AckChange")
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                       ON CONFLICT ("Hardware", "Version", "Id") DO UPDATE SET
                       "Name" = EXCLUDED."Name",
                       "Type" = EXCLUDED."Type",
                       "Mul" = EXCLUDED."Mul",
                       "Div" = EXCLUDED."Div",
                       "Step" = EXCLUDED."Step",
                       "Min" = EXCLUDED."Min",
                       "Max" = EXCLUDED."Max"''',
                    fe_type.hardware, fe_type.version, fe_type.id, fe_type.name,
                    fe_type.type, fe_type.mul, fe_type.div, fe_type.step,
                    fe_type.min_val, fe_type.max_val, fe_type.text, fe_type.acknowledge_change
                )
        
        self.logger.info(f"Сохранено {len(types)} типов переменных в БД")
    
    async def save_variable_references(self, references: List[FE_Reference]):
        """Сохранение ссылок на переменные в БД"""
        async with self.pool.acquire() as conn:
            for fe_ref in references:
                await conn.execute(
                    '''INSERT INTO "FE_References"
                       ("Hardware", "Version", "Id", "Index", "Length", "Name", "Type", "Defop")
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT ("Hardware", "Version", "Id") DO UPDATE SET
                       "Index" = EXCLUDED."Index",
                       "Length" = EXCLUDED."Length", 
                       "Name" = EXCLUDED."Name",
                       "Type" = EXCLUDED."Type",
                       "Defop" = EXCLUDED."Defop"''',
                    fe_ref.hardware, fe_ref.version, fe_ref.id, fe_ref.index,
                    fe_ref.length, fe_ref.name, fe_ref.type_id, fe_ref.defop
                )
        
        self.logger.info(f"Сохранено {len(references)} ссылок на переменные в БД")
    
    # === Хранение данных ===
    
    async def store_variable_values(self, device_id: str, values: List[VariableValue]):
        """Сохранение значений переменных в БД"""
        if not values:
            return
        
        try:
            device_uuid = uuid.UUID(device_id)
            
            async with self.pool.acquire() as conn:
                # Группируем значения по индексам для оптимизации
                grouped_values = {}
                for value in values:
                    if value.index not in grouped_values:
                        grouped_values[value.index] = []
                    grouped_values[value.index].append(value)
                
                # Сохраняем данные пакетами
                for index, index_values in grouped_values.items():
                    # Объединяем данные одного индекса
                    timestamp = index_values[0].timestamp
                    combined_data = b''.join(v.raw_data for v in index_values)
                    
                    # Вставляем в таблицу Values
                    await conn.execute(
                        '''INSERT INTO "Values" ("Did", "Index", "Stamp", "Data")
                           VALUES ($1, $2, $3, $4)''',
                        device_uuid, index, timestamp, combined_data
                    )
                    
                    # Обновляем последние значения
                    await conn.execute(
                        '''INSERT INTO "values_latest" ("Did", "Index", "Stamp", "Data")
                           VALUES ($1, $2, $3, $4)
                           ON CONFLICT ("Did", "Index") DO UPDATE SET
                           "Stamp" = EXCLUDED."Stamp",
                           "Data" = EXCLUDED."Data"
                           WHERE "values_latest"."Stamp" < EXCLUDED."Stamp"''',
                        device_uuid, index, timestamp, combined_data
                    )
            
            self.logger.debug(f"Сохранено {len(values)} значений переменных для устройства {device_id}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения значений переменных: {e}")
    
    async def get_latest_values(self, device_id: str, variable_names: List[str] = None) -> Dict[str, Any]:
        """Получение последних значений переменных"""
        try:
            device_uuid = uuid.UUID(device_id)
            
            async with self.pool.acquire() as conn:
                if variable_names:
                    # Получаем конкретные переменные
                    query = '''
                        SELECT ref."Name", val."Index", val."Data", val."Stamp"
                        FROM "values_latest" val
                        JOIN "FE_References" ref ON ref."Index" = val."Index"
                        JOIN "VersionHists" vh ON vh."Did" = val."Did"
                        WHERE val."Did" = $1 
                        AND ref."Hardware" = vh."Hardware"
                        AND ref."Version" = vh."Version"
                        AND ref."Name" = ANY($2)
                        ORDER BY val."Stamp" DESC
                    '''
                    rows = await conn.fetch(query, device_uuid, variable_names)
                else:
                    # Получаем все переменные
                    query = '''
                        SELECT ref."Name", val."Index", val."Data", val."Stamp"
                        FROM "values_latest" val
                        JOIN "FE_References" ref ON ref."Index" = val."Index"
                        JOIN "VersionHists" vh ON vh."Did" = val."Did"
                        WHERE val."Did" = $1
                        AND ref."Hardware" = vh."Hardware"
                        AND ref."Version" = vh."Version"
                        ORDER BY val."Stamp" DESC
                    '''
                    rows = await conn.fetch(query, device_uuid)
                
                # Преобразуем в словарь
                result = {}
                for row in rows:
                    result[row['Name']] = {
                        'raw_data': row['Data'],
                        'timestamp': row['Stamp'],
                        'index': row['Index']
                    }
                
                return result
                
        except Exception as e:
            self.logger.error(f"Ошибка получения значений переменных: {e}")
            return {}
    
    async def get_historical_data(self, device_id: str, variable_name: str, 
                                start_time: datetime, end_time: datetime) -> List[Tuple[datetime, bytes]]:
        """Получение исторических данных переменной"""
        try:
            device_uuid = uuid.UUID(device_id)
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    '''SELECT val."Stamp", val."Data"
                       FROM "Values" val
                       JOIN "FE_References" ref ON ref."Index" = val."Index"
                       JOIN "VersionHists" vh ON vh."Did" = val."Did"
                       WHERE val."Did" = $1
                       AND ref."Name" = $2
                       AND ref."Hardware" = vh."Hardware" 
                       AND ref."Version" = vh."Version"
                       AND val."Stamp" BETWEEN $3 AND $4
                       ORDER BY val."Stamp"''',
                    device_uuid, variable_name, start_time, end_time
                )
                
                return [(row['Stamp'], row['Data']) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Ошибка получения исторических данных: {e}")
            return []
    
    # === Система аларм ===
    
    async def log_alarm(self, device_id: str, alarm_code: int, message: str, active: bool = True):
        """Логирование аларма"""
        try:
            device_uuid = uuid.UUID(device_id)
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''INSERT INTO "AlarmLogs" ("Did", "Stamp", "AlarmCode", "Message", "Active")
                       VALUES ($1, $2, $3, $4, $5)''',
                    device_uuid, datetime.now(), alarm_code, message, active
                )
                
        except Exception as e:
            self.logger.error(f"Ошибка логирования аларма: {e}")
    
    async def get_active_alarms(self, device_id: str = None) -> List[Dict[str, Any]]:
        """Получение активных алармов"""
        try:
            async with self.pool.acquire() as conn:
                if device_id:
                    device_uuid = uuid.UUID(device_id)
                    query = '''
                        SELECT al."Did", dev."Name" as "DeviceName", al."Stamp", 
                               al."AlarmCode", al."Message"
                        FROM "AlarmLogs" al
                        JOIN "Devices" dev ON dev."Id" = al."Did"
                        WHERE al."Did" = $1 AND al."Active" = true
                        ORDER BY al."Stamp" DESC
                    '''
                    rows = await conn.fetch(query, device_uuid)
                else:
                    query = '''
                        SELECT al."Did", dev."Name" as "DeviceName", al."Stamp",
                               al."AlarmCode", al."Message"
                        FROM "AlarmLogs" al
                        JOIN "Devices" dev ON dev."Id" = al."Did"  
                        WHERE al."Active" = true
                        ORDER BY al."Stamp" DESC
                    '''
                    rows = await conn.fetch(query)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Ошибка получения алармов: {e}")
            return []
    
    # === Статистика и отчеты ===
    
    async def get_device_statistics(self, device_id: str, days: int = 7) -> Dict[str, Any]:
        """Получение статистики устройства"""
        try:
            device_uuid = uuid.UUID(device_id)
            start_time = datetime.now() - timedelta(days=days)
            
            async with self.pool.acquire() as conn:
                # Количество записей данных
                data_count = await conn.fetchval(
                    '''SELECT COUNT(*) FROM "Values" 
                       WHERE "Did" = $1 AND "Stamp" >= $2''',
                    device_uuid, start_time
                )
                
                # Количество алармов
                alarm_count = await conn.fetchval(
                    '''SELECT COUNT(*) FROM "AlarmLogs"
                       WHERE "Did" = $1 AND "Stamp" >= $2''',
                    device_uuid, start_time
                )
                
                # Последняя активность
                last_activity = await conn.fetchval(
                    '''SELECT MAX("Stamp") FROM "Values"
                       WHERE "Did" = $1''',
                    device_uuid
                )
                
                return {
                    'data_points': data_count,
                    'alarms': alarm_count,
                    'last_activity': last_activity,
                    'period_days': days
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики устройства: {e}")
            return {}
    
    async def cleanup_old_data(self, retention_days: int = 365):
        """Очистка старых данных"""
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            async with self.pool.acquire() as conn:
                # Удаляем старые значения
                deleted_values = await conn.fetchval(
                    '''DELETE FROM "Values" 
                       WHERE "Stamp" < $1
                       RETURNING COUNT(*)''',
                    cutoff_date
                )
                
                # Удаляем старые алармы
                deleted_alarms = await conn.fetchval(
                    '''DELETE FROM "AlarmLogs"
                       WHERE "Stamp" < $1 AND "Active" = false
                       RETURNING COUNT(*)''',
                    cutoff_date
                )
                
                self.logger.info(f"Очистка БД: удалено {deleted_values} записей данных, {deleted_alarms} алармов")
                
        except Exception as e:
            self.logger.error(f"Ошибка очистки старых данных: {e}")

class DatabaseIntegratedGateway:
    """
    Гейтвей с интеграцией БД
    Расширяет StienenGatewayBackend для работы с PostgreSQL
    """
    
    def __init__(self, gateway_backend, db_config: DatabaseConfig):
        self.gateway = gateway_backend
        self.db = DatabaseManager(db_config)
        self.logger = logging.getLogger(__name__)
        
        # Кэш для загруженных переменных
        self._variables_cache = {}
        
        # Задачи фоновой обработки
        self.db_tasks = []
    
    async def initialize(self) -> bool:
        """Инициализация с БД"""
        # Инициализируем БД
        if not await self.db.initialize():
            return False
        
        # Регистрируем гейтвей
        gateway_id = await self.db.register_gateway(
            self.gateway.config.name, 
            f"Stienen RS485 Gateway на {self.gateway.config.rs485_port}"
        )
        
        # Загружаем переменные из БД для всех устройств
        await self._load_variables_from_db()
        
        # Запускаем фоновые задачи
        self._start_background_tasks()
        
        return True
    
    async def _load_variables_from_db(self):
        """Загрузка переменных из БД"""
        # Получаем уникальные версии оборудования
        hardware_versions = set()
        for device in self.gateway.devices.values():
            hardware_versions.add((device.hardware, device.version))
        
        # Загружаем переменные для каждой версии
        for hardware, version in hardware_versions:
            types = await self.db.load_variable_types(hardware, version)
            references = await self.db.load_variable_references(hardware, version)
            
            # Регистрируем в мапере
            for fe_type in types:
                self.gateway.variable_mapper.register_type(fe_type)
            
            for fe_ref in references:
                self.gateway.variable_mapper.register_reference(fe_ref)
            
            self._variables_cache[(hardware, version)] = {
                'types': types,
                'references': references
            }
            
            self.logger.info(f"Загружены переменные HW{hardware}.{version}: {len(types)} типов, {len(references)} ссылок")
    
    def _start_background_tasks(self):
        """Запуск фоновых задач БД"""
        # Задача сохранения данных
        save_task = asyncio.create_task(self._data_save_loop())
        self.db_tasks.append(save_task)
        
        # Задача обновления информации об устройствах
        update_task = asyncio.create_task(self._device_info_update_loop())
        self.db_tasks.append(update_task)
        
        # Задача очистки старых данных (раз в день)
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.db_tasks.append(cleanup_task)
    
    async def _data_save_loop(self):
        """Цикл сохранения данных в БД"""
        while True:
            try:
                # Сохраняем данные всех устройств
                for device_id, device_manager in self.gateway.device_managers.items():
                    # Получаем все текущие значения
                    current_values = device_manager.get_all_current_values()
                    
                    if current_values:
                        # Преобразуем в VariableValue объекты
                        variable_values = []
                        for var_name, value in current_values.items():
                            # Получаем информацию о переменной
                            device = next(d for d in self.gateway.devices.values() if d.device_id == device_id)
                            reference = self.gateway.variable_mapper.get_reference_by_name(
                                device.hardware, device.version, var_name
                            )
                            
                            if reference:
                                var_value = VariableValue(
                                    device_id=device_id,
                                    index=reference.index,
                                    timestamp=datetime.now(),
                                    raw_data=self.gateway.variable_mapper.convert_value_to_raw(
                                        value, 
                                        self.gateway.variable_mapper.get_type(device.hardware, device.version, reference.type_id)
                                    ),
                                    converted_value=value
                                )
                                variable_values.append(var_value)
                        
                        # Сохраняем в БД
                        await self.db.store_variable_values(device_id, variable_values)
                
                # Ждем 30 секунд до следующего сохранения
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Ошибка в цикле сохранения данных: {e}")
                await asyncio.sleep(60)
    
    async def _device_info_update_loop(self):
        """Цикл обновления информации об устройствах"""
        while True:
            try:
                # Обновляем информацию всех устройств
                for device in self.gateway.devices.values():
                    await self.db.update_device_info(device)
                
                # Ждем 5 минут
                await asyncio.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Ошибка обновления информации об устройствах: {e}")
                await asyncio.sleep(600)
    
    async def _cleanup_loop(self):
        """Цикл очистки старых данных"""
        while True:
            try:
                # Очистка раз в день в 2:00
                now = datetime.now()
                if now.hour == 2 and now.minute < 10:
                    await self.db.cleanup_old_data(retention_days=365)
                
                # Ждем час
                await asyncio.sleep(3600)
                
            except Exception as e:
                self.logger.error(f"Ошибка очистки данных: {e}")
                await asyncio.sleep(3600)
    
    async def add_device_with_db(self, address: int, name: str, hardware: int = 1001, version: int = 1):
        """Добавление устройства с регистрацией в БД"""
        # Добавляем устройство в гейтвей
        await self.gateway.add_device(address, name, hardware, version)
        
        # Регистрируем в БД
        device = self.gateway.devices.get(address)
        if device:
            gateway_info = await self.db.get_gateway_by_name(self.gateway.config.name)
            if gateway_info:
                await self.db.register_device(device, str(gateway_info['Id']))
    
    async def get_device_history(self, address: int, variable_name: str, hours: int = 24) -> List[Tuple[datetime, Any]]:
        """Получение истории переменной устройства"""
        device = self.gateway.devices.get(address)
        if not device:
            return []
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # Получаем сырые данные из БД
        raw_history = await self.db.get_historical_data(device.device_id, variable_name, start_time, end_time)
        
        # Конвертируем в типизированные значения
        reference = self.gateway.variable_mapper.get_reference_by_name(device.hardware, device.version, variable_name)
        if not reference:
            return raw_history
        
        var_type = self.gateway.variable_mapper.get_type(device.hardware, device.version, reference.type_id)
        if not var_type:
            return raw_history
        
        converted_history = []
        for timestamp, raw_data in raw_history:
            converted_value = self.gateway.variable_mapper.convert_raw_to_value(raw_data, var_type)
            converted_history.append((timestamp, converted_value))
        
        return converted_history
    
    async def shutdown(self):
        """Корректное завершение работы"""
        # Останавливаем фоновые задачи БД
        for task in self.db_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Закрываем БД
        await self.db.close()
        
        # Завершаем гейтвей
        await self.gateway.shutdown()

# CLI для работы с БД
async def cli_database_operations():
    """CLI утилиты для работы с БД"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Операции с базой данных")
    parser.add_argument('operation', choices=['init', 'migrate', 'cleanup', 'stats'])
    parser.add_argument('--host', default='localhost', help='Хост PostgreSQL')
    parser.add_argument('--port', type=int, default=5432, help='Порт PostgreSQL')
    parser.add_argument('--database', default='stienen', help='Имя БД')
    parser.add_argument('--username', default='stienen', help='Пользователь БД')
    parser.add_argument('--password', help='Пароль БД')
    parser.add_argument('--config', help='JSON файл с переменными для миграции')
    
    args = parser.parse_args()
    
    # Создаем конфигурацию БД
    db_config = DatabaseConfig(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.username,
        password=args.password or input("Пароль БД: ")
    )
    
    db = DatabaseManager(db_config)
    
    try:
        if not await db.initialize():
            print("❌ Не удалось подключиться к БД")
            return 1
        
        if args.operation == 'init':
            # Инициализация схемы БД
            print("🔧 Инициализация схемы БД...")
            # Здесь можно добавить создание таблиц если их нет
            
        elif args.operation == 'migrate':
            # Миграция переменных из JSON в БД
            if not args.config:
                print("❌ Укажите --config для миграции")
                return 1
            
            print(f"📦 Миграция переменных из {args.config}...")
            with open(args.config, 'r') as f:
                config = json.load(f)
            
            # Загружаем типы и ссылки
            if 'types' in config:
                types = [FE_Type(**t) for t in config['types']]
                await db.save_variable_types(types)
                print(f"✅ Мигрировано {len(types)} типов переменных")
            
            if 'references' in config:
                references = [FE_Reference(**r) for r in config['references']]
                await db.save_variable_references(references)
                print(f"✅ Мигрировано {len(references)} ссылок на переменные")
        
        elif args.operation == 'cleanup':
            # Очистка старых данных
            print("🧹 Очистка старых данных...")
            await db.cleanup_old_data(retention_days=365)
            print("✅ Очистка завершена")
        
        elif args.operation == 'stats':
            # Показ статистики БД
            print("📊 Статистика базы данных:")
            async with db.pool.acquire() as conn:
                # Количество устройств
                devices_count = await conn.fetchval('SELECT COUNT(*) FROM "Devices"')
                print(f"  Устройств: {devices_count}")
                
                # Количество записей данных
                values_count = await conn.fetchval('SELECT COUNT(*) FROM "Values"')
                print(f"  Записей данных: {values_count}")
                
                # Количество алармов
                alarms_count = await conn.fetchval('SELECT COUNT(*) FROM "AlarmLogs"')
                print(f"  Алармов: {alarms_count}")
                
                # Размер БД
                db_size = await conn.fetchval(
                    "SELECT pg_size_pretty(pg_database_size($1))", args.database
                )
                print(f"  Размер БД: {db_size}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return 1
    finally:
        await db.close()

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(cli_database_operations())
    sys.exit(exit_code)
