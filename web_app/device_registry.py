#!/usr/bin/env python3
"""
Device Registry - управление регистрацией и метаданными устройств
Аналог системы регистрации устройств IXON
"""

import sqlite3
import json
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import os

logger = logging.getLogger(__name__)

@dataclass
class RegisteredDevice:
    """Зарегистрированное устройство в системе"""
    device_id: str
    hostname: str
    tailscale_ip: str
    auth_key_hash: str  # Хэш ключа авторизации
    registration_time: str
    last_seen: str
    status: str  # 'pending', 'active', 'inactive', 'revoked'
    device_type: str  # 'farm', 'mobile', 'gateway'
    metadata: Dict[str, Any]
    tags: List[str]
    owner_email: str = ""
    notes: str = ""

@dataclass
class AuthKey:
    """Ключ авторизации для устройств"""
    key_id: str
    key_hash: str
    created_time: str
    expires_time: str
    usage_count: int
    max_usage: int  # -1 для неограниченного использования
    is_reusable: bool
    is_ephemeral: bool
    tags: List[str]
    created_by: str = "system"
    status: str = "active"  # 'active', 'expired', 'revoked'

@dataclass
class DeviceRegistrationRequest:
    """Запрос на регистрацию устройства"""
    request_id: str
    auth_key_hash: str
    device_hostname: str
    device_type: str
    device_info: Dict[str, Any]
    requested_time: str
    tailscale_ip: str = ""
    status: str = "pending"  # 'pending', 'approved', 'rejected'
    approved_by: str = ""
    approved_time: str = ""

class DeviceRegistry:
    """Реестр устройств с управлением регистрацией"""
    
    def __init__(self, db_path: str = "device_registry.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS registered_devices (
                        device_id TEXT PRIMARY KEY,
                        hostname TEXT NOT NULL,
                        tailscale_ip TEXT,
                        auth_key_hash TEXT NOT NULL,
                        registration_time TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        device_type TEXT DEFAULT 'farm',
                        metadata TEXT DEFAULT '{}',
                        tags TEXT DEFAULT '[]',
                        owner_email TEXT DEFAULT '',
                        notes TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_keys (
                        key_id TEXT PRIMARY KEY,
                        key_hash TEXT NOT NULL UNIQUE,
                        created_time TEXT NOT NULL,
                        expires_time TEXT,
                        usage_count INTEGER DEFAULT 0,
                        max_usage INTEGER DEFAULT -1,
                        is_reusable BOOLEAN DEFAULT 1,
                        is_ephemeral BOOLEAN DEFAULT 0,
                        tags TEXT DEFAULT '[]',
                        created_by TEXT DEFAULT 'system',
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS device_registration_requests (
                        request_id TEXT PRIMARY KEY,
                        auth_key_hash TEXT NOT NULL,
                        device_hostname TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_info TEXT NOT NULL,
                        requested_time TEXT NOT NULL,
                        tailscale_ip TEXT DEFAULT '',
                        status TEXT DEFAULT 'pending',
                        approved_by TEXT DEFAULT '',
                        approved_time TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (auth_key_hash) REFERENCES auth_keys (key_hash)
                    )
                """)
                
                # Индексы для производительности
                conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON registered_devices(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON registered_devices(device_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_tailscale_ip ON registered_devices(tailscale_ip)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_keys_status ON auth_keys(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON device_registration_requests(status)")
                
                conn.commit()
                logger.info("База данных реестра устройств инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
            raise
    
    def generate_auth_key(self, 
                         expires_hours: int = 24,
                         max_usage: int = -1,
                         is_reusable: bool = True,
                         is_ephemeral: bool = False,
                         tags: List[str] = None,
                         created_by: str = "system") -> str:
        """Генерация ключа авторизации"""
        if tags is None:
            tags = ["farm"]
        
        # Генерируем уникальный ключ
        key = f"tskey-{secrets.token_urlsafe(32)}"
        key_id = secrets.token_urlsafe(16)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        now = datetime.now()
        expires_time = (now + timedelta(hours=expires_hours)).isoformat() if expires_hours > 0 else ""
        
        auth_key = AuthKey(
            key_id=key_id,
            key_hash=key_hash,
            created_time=now.isoformat(),
            expires_time=expires_time,
            usage_count=0,
            max_usage=max_usage,
            is_reusable=is_reusable,
            is_ephemeral=is_ephemeral,
            tags=tags,
            created_by=created_by
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO auth_keys 
                    (key_id, key_hash, created_time, expires_time, usage_count, max_usage, 
                     is_reusable, is_ephemeral, tags, created_by, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    auth_key.key_id,
                    auth_key.key_hash,
                    auth_key.created_time,
                    auth_key.expires_time,
                    auth_key.usage_count,
                    auth_key.max_usage,
                    auth_key.is_reusable,
                    auth_key.is_ephemeral,
                    json.dumps(auth_key.tags),
                    auth_key.created_by,
                    auth_key.status
                ))
                conn.commit()
                
                logger.info(f"Создан auth key {key_id} для {created_by}")
                return key
                
        except Exception as e:
            logger.error(f"Ошибка создания auth key: {e}")
            raise
    
    def validate_auth_key(self, auth_key: str) -> Optional[AuthKey]:
        """Валидация и получение информации о ключе"""
        key_hash = hashlib.sha256(auth_key.encode()).hexdigest()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT * FROM auth_keys WHERE key_hash = ? AND status = 'active'
                """, (key_hash,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Парсим данные
                auth_key_data = AuthKey(
                    key_id=row[0],
                    key_hash=row[1],
                    created_time=row[2],
                    expires_time=row[3] or "",
                    usage_count=row[4],
                    max_usage=row[5],
                    is_reusable=bool(row[6]),
                    is_ephemeral=bool(row[7]),
                    tags=json.loads(row[8] or "[]"),
                    created_by=row[9],
                    status=row[10]
                )
                
                # Проверка срока действия
                if auth_key_data.expires_time:
                    expires = datetime.fromisoformat(auth_key_data.expires_time)
                    if datetime.now() > expires:
                        # Помечаем ключ как истекший
                        conn.execute("""
                            UPDATE auth_keys SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                            WHERE key_hash = ?
                        """, (key_hash,))
                        conn.commit()
                        return None
                
                # Проверка лимита использования
                if auth_key_data.max_usage > 0 and auth_key_data.usage_count >= auth_key_data.max_usage:
                    return None
                
                return auth_key_data
                
        except Exception as e:
            logger.error(f"Ошибка валидации auth key: {e}")
            return None
    
    def create_registration_request(self, 
                                  auth_key: str,
                                  device_hostname: str,
                                  device_type: str,
                                  device_info: Dict[str, Any],
                                  tailscale_ip: str = "") -> str:
        """Создание запроса на регистрацию устройства"""
        
        # Валидация ключа
        auth_key_data = self.validate_auth_key(auth_key)
        if not auth_key_data:
            raise ValueError("Недействительный или истекший ключ авторизации")
        
        request_id = secrets.token_urlsafe(16)
        key_hash = hashlib.sha256(auth_key.encode()).hexdigest()
        
        registration_request = DeviceRegistrationRequest(
            request_id=request_id,
            auth_key_hash=key_hash,
            device_hostname=device_hostname,
            device_type=device_type,
            device_info=device_info,
            requested_time=datetime.now().isoformat(),
            tailscale_ip=tailscale_ip
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO device_registration_requests
                    (request_id, auth_key_hash, device_hostname, device_type, device_info, 
                     requested_time, tailscale_ip, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    registration_request.request_id,
                    registration_request.auth_key_hash,
                    registration_request.device_hostname,
                    registration_request.device_type,
                    json.dumps(registration_request.device_info),
                    registration_request.requested_time,
                    registration_request.tailscale_ip,
                    registration_request.status
                ))
                
                # Увеличиваем счетчик использования ключа
                conn.execute("""
                    UPDATE auth_keys 
                    SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE key_hash = ?
                """, (key_hash,))
                
                conn.commit()
                
                logger.info(f"Создан запрос на регистрацию {request_id} для {device_hostname}")
                return request_id
                
        except Exception as e:
            logger.error(f"Ошибка создания запроса регистрации: {e}")
            raise
    
    def approve_registration_request(self, 
                                   request_id: str,
                                   approved_by: str = "system",
                                   additional_metadata: Dict[str, Any] = None) -> bool:
        """Одобрение запроса на регистрацию"""
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Получаем запрос
                cursor = conn.execute("""
                    SELECT * FROM device_registration_requests 
                    WHERE request_id = ? AND status = 'pending'
                """, (request_id,))
                
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"Запрос регистрации {request_id} не найден или уже обработан")
                    return False
                
                # Парсим данные запроса
                request_data = DeviceRegistrationRequest(
                    request_id=row[0],
                    auth_key_hash=row[1],
                    device_hostname=row[2],
                    device_type=row[3],
                    device_info=json.loads(row[4]),
                    requested_time=row[5],
                    tailscale_ip=row[6],
                    status=row[7]
                )
                
                # Создаем устройство
                device_id = secrets.token_urlsafe(16)
                now = datetime.now().isoformat()
                
                # Объединяем метаданные
                metadata = request_data.device_info.copy()
                if additional_metadata:
                    metadata.update(additional_metadata)
                
                # Получаем теги из auth key
                cursor = conn.execute("""
                    SELECT tags FROM auth_keys WHERE key_hash = ?
                """, (request_data.auth_key_hash,))
                tags_row = cursor.fetchone()
                tags = json.loads(tags_row[0] if tags_row else "[]")
                
                device = RegisteredDevice(
                    device_id=device_id,
                    hostname=request_data.device_hostname,
                    tailscale_ip=request_data.tailscale_ip,
                    auth_key_hash=request_data.auth_key_hash,
                    registration_time=now,
                    last_seen=now,
                    status='active',
                    device_type=request_data.device_type,
                    metadata=metadata,
                    tags=tags
                )
                
                # Добавляем устройство в реестр
                conn.execute("""
                    INSERT INTO registered_devices
                    (device_id, hostname, tailscale_ip, auth_key_hash, registration_time, 
                     last_seen, status, device_type, metadata, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device.device_id,
                    device.hostname,
                    device.tailscale_ip,
                    device.auth_key_hash,
                    device.registration_time,
                    device.last_seen,
                    device.status,
                    device.device_type,
                    json.dumps(device.metadata),
                    json.dumps(device.tags)
                ))
                
                # Обновляем статус запроса
                conn.execute("""
                    UPDATE device_registration_requests
                    SET status = 'approved', approved_by = ?, approved_time = ?, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE request_id = ?
                """, (approved_by, now, request_id))
                
                conn.commit()
                
                logger.info(f"Запрос регистрации {request_id} одобрен, создано устройство {device_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка одобрения регистрации: {e}")
            return False
    
    def get_pending_registration_requests(self) -> List[DeviceRegistrationRequest]:
        """Получение ожидающих одобрения запросов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT * FROM device_registration_requests 
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                """)
                
                requests = []
                for row in cursor.fetchall():
                    request = DeviceRegistrationRequest(
                        request_id=row[0],
                        auth_key_hash=row[1],
                        device_hostname=row[2],
                        device_type=row[3],
                        device_info=json.loads(row[4]),
                        requested_time=row[5],
                        tailscale_ip=row[6],
                        status=row[7],
                        approved_by=row[8],
                        approved_time=row[9]
                    )
                    requests.append(request)
                
                return requests
                
        except Exception as e:
            logger.error(f"Ошибка получения запросов регистрации: {e}")
            return []
    
    def get_registered_devices(self, 
                             device_type: str = None,
                             status: str = None) -> List[RegisteredDevice]:
        """Получение зарегистрированных устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = "SELECT * FROM registered_devices WHERE 1=1"
                params = []
                
                if device_type:
                    query += " AND device_type = ?"
                    params.append(device_type)
                
                if status:
                    query += " AND status = ?"
                    params.append(status)
                
                query += " ORDER BY registration_time DESC"
                
                cursor = conn.execute(query, params)
                
                devices = []
                for row in cursor.fetchall():
                    device = RegisteredDevice(
                        device_id=row[0],
                        hostname=row[1],
                        tailscale_ip=row[2],
                        auth_key_hash=row[3],
                        registration_time=row[4],
                        last_seen=row[5],
                        status=row[6],
                        device_type=row[7],
                        metadata=json.loads(row[8] or "{}"),
                        tags=json.loads(row[9] or "[]"),
                        owner_email=row[10] or "",
                        notes=row[11] or ""
                    )
                    devices.append(device)
                
                return devices
                
        except Exception as e:
            logger.error(f"Ошибка получения устройств: {e}")
            return []
    
    def update_device_last_seen(self, device_id: str, tailscale_ip: str = None) -> bool:
        """Обновление времени последней активности устройства"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                params = [datetime.now().isoformat(), device_id]
                query = """
                    UPDATE registered_devices 
                    SET last_seen = ?, updated_at = CURRENT_TIMESTAMP
                """
                
                if tailscale_ip:
                    query += ", tailscale_ip = ?"
                    params.insert(1, tailscale_ip)
                
                query += " WHERE device_id = ?"
                
                conn.execute(query, params)
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления last_seen для {device_id}: {e}")
            return False
    
    def revoke_device(self, device_id: str, reason: str = "") -> bool:
        """Отзыв устройства из системы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                metadata_update = {"revoked_reason": reason, "revoked_time": datetime.now().isoformat()}
                
                # Получаем текущие метаданные
                cursor = conn.execute("SELECT metadata FROM registered_devices WHERE device_id = ?", (device_id,))
                row = cursor.fetchone()
                if row:
                    current_metadata = json.loads(row[0] or "{}")
                    current_metadata.update(metadata_update)
                    
                    conn.execute("""
                        UPDATE registered_devices 
                        SET status = 'revoked', metadata = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE device_id = ?
                    """, (json.dumps(current_metadata), device_id))
                    
                    conn.commit()
                    logger.info(f"Устройство {device_id} отозвано: {reason}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Ошибка отзыва устройства {device_id}: {e}")
            return False
    
    def get_device_stats(self) -> Dict[str, Any]:
        """Получение статистики устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Общая статистика
                cursor = conn.execute("SELECT COUNT(*) FROM registered_devices")
                total_devices = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM registered_devices WHERE status = 'active'")
                active_devices = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM device_registration_requests WHERE status = 'pending'")
                pending_requests = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM auth_keys WHERE status = 'active'")
                active_keys = cursor.fetchone()[0]
                
                # Статистика по типам
                cursor = conn.execute("""
                    SELECT device_type, COUNT(*) 
                    FROM registered_devices 
                    WHERE status = 'active'
                    GROUP BY device_type
                """)
                devices_by_type = dict(cursor.fetchall())
                
                return {
                    "total_devices": total_devices,
                    "active_devices": active_devices,
                    "pending_requests": pending_requests,
                    "active_auth_keys": active_keys,
                    "devices_by_type": devices_by_type,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

# Глобальный экземпляр реестра
_device_registry: Optional[DeviceRegistry] = None

def get_device_registry() -> DeviceRegistry:
    """Получение глобального экземпляра реестра устройств"""
    global _device_registry
    if not _device_registry:
        # Путь к БД в директории веб-приложения
        db_path = os.path.join(os.path.dirname(__file__), "device_registry.db")
        _device_registry = DeviceRegistry(db_path)
    return _device_registry

# Пример использования
if __name__ == "__main__":
    registry = DeviceRegistry("test_device_registry.db")
    
    print("=== Тест системы регистрации устройств ===")
    
    # Создание auth key
    print("1. Создание auth key...")
    auth_key = registry.generate_auth_key(
        expires_hours=24,
        is_reusable=True,
        tags=["farm", "test"],
        created_by="admin"
    )
    print(f"Создан ключ: {auth_key[:20]}...")
    
    # Создание запроса на регистрацию
    print("\n2. Создание запроса на регистрацию...")
    request_id = registry.create_registration_request(
        auth_key=auth_key,
        device_hostname="farm-001",
        device_type="farm",
        device_info={
            "os": "Linux",
            "version": "1.0.0",
            "location": "Теплица #1",
            "capabilities": ["kub1063", "monitoring"]
        },
        tailscale_ip="100.64.1.10"
    )
    print(f"Создан запрос: {request_id}")
    
    # Одобрение запроса
    print("\n3. Одобрение запроса...")
    success = registry.approve_registration_request(
        request_id=request_id,
        approved_by="admin",
        additional_metadata={"approved_location": "Основная теплица"}
    )
    print(f"Запрос одобрен: {success}")
    
    # Получение статистики
    print("\n4. Статистика системы:")
    stats = registry.get_device_stats()
    for key, value in stats.items():
        if key != "timestamp":
            print(f"  {key}: {value}")
    
    # Получение устройств
    print("\n5. Зарегистрированные устройства:")
    devices = registry.get_registered_devices()
    for device in devices:
        print(f"  📱 {device.hostname} ({device.device_type}) - {device.status}")
        print(f"     IP: {device.tailscale_ip}, Теги: {device.tags}")
    
    print("\n✅ Тест завершен")