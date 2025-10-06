#!/usr/bin/env python3
"""
Device Registry - управление регистрацией и метаданными устройств
Аналог системы регистрации устройств IXON
Ported from archive to SERVER for centralized device management
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Optional, List

# Import SERVER security components
try:
    from ..security.mitm_protection import validate_certificate_fingerprint
except ImportError:
    validate_certificate_fingerprint = None

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
    device_type: str  # 'farm', 'mobile', 'gateway', 'edge'
    metadata: dict[str, Any]
    tags: list[str]
    owner_email: str = ""
    notes: str = ""
    certificate_fingerprint: str = ""  # Для certificate pinning
    capabilities: list[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


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
    tags: list[str]
    created_by: str = "system"
    status: str = "active"  # 'active', 'expired', 'revoked'
    device_types: list[str] = None  # Разрешенные типы устройств

    def __post_init__(self):
        if self.device_types is None:
            self.device_types = ["farm", "mobile", "gateway", "edge"]


@dataclass
class DeviceRegistrationRequest:
    """Запрос на регистрацию устройства"""

    request_id: str
    auth_key_hash: str
    device_hostname: str
    device_type: str
    device_info: dict[str, Any]
    requested_time: str
    tailscale_ip: str = ""
    status: str = "pending"  # 'pending', 'approved', 'rejected'
    approved_by: str = ""
    approved_time: str = ""
    certificate_fingerprint: str = ""
    capabilities: list[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


class DeviceRegistry:
    """Реестр устройств с управлением регистрацией"""

    def __init__(self, db_path: str = "device_registry.db"):
        self.db_path = db_path
        self.init_database()
        logger.info(f"🗄️ Device Registry инициализирован: {db_path}")

    def init_database(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица зарегистрированных устройств
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registered_devices (
                        device_id TEXT PRIMARY KEY,
                        hostname TEXT NOT NULL,
                        tailscale_ip TEXT,
                        auth_key_hash TEXT NOT NULL,
                        registration_time TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        status TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        metadata TEXT,
                        tags TEXT,
                        owner_email TEXT,
                        notes TEXT,
                        certificate_fingerprint TEXT,
                        capabilities TEXT
                    )
                    """
                )
                
                # Таблица ключей авторизации
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_keys (
                        key_id TEXT PRIMARY KEY,
                        key_hash TEXT NOT NULL,
                        created_time TEXT NOT NULL,
                        expires_time TEXT,
                        usage_count INTEGER DEFAULT 0,
                        max_usage INTEGER DEFAULT -1,
                        is_reusable BOOLEAN DEFAULT TRUE,
                        is_ephemeral BOOLEAN DEFAULT FALSE,
                        tags TEXT,
                        created_by TEXT,
                        status TEXT DEFAULT 'active',
                        device_types TEXT
                    )
                    """
                )
                
                # Таблица запросов на регистрацию
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registration_requests (
                        request_id TEXT PRIMARY KEY,
                        auth_key_hash TEXT NOT NULL,
                        device_hostname TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_info TEXT NOT NULL,
                        requested_time TEXT NOT NULL,
                        tailscale_ip TEXT,
                        status TEXT DEFAULT 'pending',
                        approved_by TEXT,
                        approved_time TEXT,
                        certificate_fingerprint TEXT,
                        capabilities TEXT
                    )
                    """
                )
                
                # Индексы для оптимизации поиска
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON registered_devices(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON registered_devices(device_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON registration_requests(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_keys_status ON auth_keys(status)")
                
                conn.commit()
                logger.info("✅ База данных Device Registry инициализирована")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
            raise

    def create_auth_key(
        self, 
        device_types: list[str] = None, 
        max_usage: int = -1, 
        expires_in_hours: int = None,
        is_reusable: bool = True,
        tags: list[str] = None,
        created_by: str = "admin"
    ) -> tuple[str, str]:
        """Создание ключа авторизации"""
        try:
            # Генерируем уникальный ключ
            auth_key = secrets.token_urlsafe(32)
            key_id = secrets.token_urlsafe(16)
            key_hash = hashlib.sha256(auth_key.encode()).hexdigest()
            
            created_time = datetime.now().isoformat()
            expires_time = None
            if expires_in_hours:
                expires_time = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
            
            if device_types is None:
                device_types = ["farm", "mobile", "gateway", "edge"]
            if tags is None:
                tags = []
            
            auth_key_obj = AuthKey(
                key_id=key_id,
                key_hash=key_hash,
                created_time=created_time,
                expires_time=expires_time,
                usage_count=0,
                max_usage=max_usage,
                is_reusable=is_reusable,
                is_ephemeral=False,
                tags=tags,
                created_by=created_by,
                device_types=device_types
            )
            
            # Сохраняем в базу данных
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO auth_keys (
                        key_id, key_hash, created_time, expires_time, usage_count,
                        max_usage, is_reusable, is_ephemeral, tags, created_by,
                        status, device_types
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        auth_key_obj.key_id,
                        auth_key_obj.key_hash,
                        auth_key_obj.created_time,
                        auth_key_obj.expires_time,
                        auth_key_obj.usage_count,
                        auth_key_obj.max_usage,
                        auth_key_obj.is_reusable,
                        auth_key_obj.is_ephemeral,
                        json.dumps(auth_key_obj.tags),
                        auth_key_obj.created_by,
                        auth_key_obj.status,
                        json.dumps(auth_key_obj.device_types)
                    )
                )
                conn.commit()
            
            logger.info(f"🔑 Создан ключ авторизации {key_id} для типов устройств: {device_types}")
            return key_id, auth_key
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания ключа авторизации: {e}")
            raise

    def validate_auth_key(self, auth_key: str, device_type: str = None) -> Optional[AuthKey]:
        """Проверка и валидация ключа авторизации"""
        try:
            key_hash = hashlib.sha256(auth_key.encode()).hexdigest()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT key_id, key_hash, created_time, expires_time, usage_count,
                           max_usage, is_reusable, is_ephemeral, tags, created_by,
                           status, device_types
                    FROM auth_keys 
                    WHERE key_hash = ? AND status = 'active'
                    """,
                    (key_hash,)
                )
                
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"⚠️ Недействительный ключ авторизации")
                    return None
                
                auth_key_obj = AuthKey(
                    key_id=row[0],
                    key_hash=row[1],
                    created_time=row[2],
                    expires_time=row[3],
                    usage_count=row[4],
                    max_usage=row[5],
                    is_reusable=bool(row[6]),
                    is_ephemeral=bool(row[7]),
                    tags=json.loads(row[8]) if row[8] else [],
                    created_by=row[9],
                    status=row[10],
                    device_types=json.loads(row[11]) if row[11] else []
                )
                
                # Проверяем срок действия
                if auth_key_obj.expires_time:
                    expires = datetime.fromisoformat(auth_key_obj.expires_time)
                    if datetime.now() > expires:
                        logger.warning(f"⚠️ Ключ авторизации {auth_key_obj.key_id} истек")
                        return None
                
                # Проверяем лимит использования
                if auth_key_obj.max_usage != -1 and auth_key_obj.usage_count >= auth_key_obj.max_usage:
                    logger.warning(f"⚠️ Ключ авторизации {auth_key_obj.key_id} исчерпан")
                    return None
                
                # Проверяем разрешенные типы устройств
                if device_type and device_type not in auth_key_obj.device_types:
                    logger.warning(f"⚠️ Тип устройства {device_type} не разрешен для ключа {auth_key_obj.key_id}")
                    return None
                
                logger.debug(f"✅ Ключ авторизации {auth_key_obj.key_id} валиден")
                return auth_key_obj
                
        except Exception as e:
            logger.error(f"❌ Ошибка валидации ключа авторизации: {e}")
            return None

    def register_device_request(
        self,
        auth_key: str,
        hostname: str,
        device_type: str,
        device_info: dict,
        tailscale_ip: str = "",
        certificate_fingerprint: str = "",
        capabilities: list[str] = None
    ) -> Optional[str]:
        """Создание запроса на регистрацию устройства"""
        try:
            # Валидируем ключ авторизации
            auth_key_obj = self.validate_auth_key(auth_key, device_type)
            if not auth_key_obj:
                logger.error("❌ Недействительный ключ авторизации")
                return None
            
            # Генерируем ID запроса
            request_id = secrets.token_urlsafe(16)
            
            if capabilities is None:
                capabilities = []
            
            # Создаем запрос
            request = DeviceRegistrationRequest(
                request_id=request_id,
                auth_key_hash=auth_key_obj.key_hash,
                device_hostname=hostname,
                device_type=device_type,
                device_info=device_info,
                requested_time=datetime.now().isoformat(),
                tailscale_ip=tailscale_ip,
                certificate_fingerprint=certificate_fingerprint,
                capabilities=capabilities
            )
            
            # Сохраняем запрос в базу данных
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO registration_requests (
                        request_id, auth_key_hash, device_hostname, device_type,
                        device_info, requested_time, tailscale_ip, status,
                        certificate_fingerprint, capabilities
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.request_id,
                        request.auth_key_hash,
                        request.device_hostname,
                        request.device_type,
                        json.dumps(request.device_info),
                        request.requested_time,
                        request.tailscale_ip,
                        request.status,
                        request.certificate_fingerprint,
                        json.dumps(request.capabilities)
                    )
                )
                
                # Увеличиваем счетчик использования ключа
                cursor.execute(
                    "UPDATE auth_keys SET usage_count = usage_count + 1 WHERE key_hash = ?",
                    (auth_key_obj.key_hash,)
                )
                
                conn.commit()
            
            logger.info(f"📝 Создан запрос на регистрацию устройства {request_id} ({device_type}: {hostname})")
            return request_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания запроса на регистрацию: {e}")
            return None

    def approve_device_registration(self, request_id: str, approved_by: str = "admin") -> bool:
        """Одобрение регистрации устройства"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем запрос на регистрацию
                cursor.execute(
                    """
                    SELECT request_id, auth_key_hash, device_hostname, device_type,
                           device_info, requested_time, tailscale_ip, status,
                           certificate_fingerprint, capabilities
                    FROM registration_requests 
                    WHERE request_id = ? AND status = 'pending'
                    """,
                    (request_id,)
                )
                
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"⚠️ Запрос на регистрацию {request_id} не найден или уже обработан")
                    return False
                
                # Создаем зарегистрированное устройство
                device_id = secrets.token_urlsafe(16)
                current_time = datetime.now().isoformat()
                
                device_info = json.loads(row[4]) if row[4] else {}
                capabilities = json.loads(row[9]) if row[9] else []
                
                registered_device = RegisteredDevice(
                    device_id=device_id,
                    hostname=row[2],
                    tailscale_ip=row[6],
                    auth_key_hash=row[1],
                    registration_time=current_time,
                    last_seen=current_time,
                    status="active",
                    device_type=row[3],
                    metadata=device_info,
                    tags=[row[3], "auto_approved"],
                    certificate_fingerprint=row[8] or "",
                    capabilities=capabilities
                )
                
                # Сохраняем зарегистрированное устройство
                cursor.execute(
                    """
                    INSERT INTO registered_devices (
                        device_id, hostname, tailscale_ip, auth_key_hash,
                        registration_time, last_seen, status, device_type,
                        metadata, tags, owner_email, notes, certificate_fingerprint,
                        capabilities
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        registered_device.device_id,
                        registered_device.hostname,
                        registered_device.tailscale_ip,
                        registered_device.auth_key_hash,
                        registered_device.registration_time,
                        registered_device.last_seen,
                        registered_device.status,
                        registered_device.device_type,
                        json.dumps(registered_device.metadata),
                        json.dumps(registered_device.tags),
                        registered_device.owner_email,
                        registered_device.notes,
                        registered_device.certificate_fingerprint,
                        json.dumps(registered_device.capabilities)
                    )
                )
                
                # Обновляем статус запроса
                cursor.execute(
                    """
                    UPDATE registration_requests 
                    SET status = 'approved', approved_by = ?, approved_time = ?
                    WHERE request_id = ?
                    """,
                    (approved_by, current_time, request_id)
                )
                
                conn.commit()
            
            logger.info(f"✅ Устройство {device_id} ({registered_device.hostname}) одобрено и зарегистрировано")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка одобрения регистрации устройства {request_id}: {e}")
            return False

    def get_all_devices(self) -> List[RegisteredDevice]:
        """Получение списка всех зарегистрированных устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT device_id, hostname, tailscale_ip, auth_key_hash,
                           registration_time, last_seen, status, device_type,
                           metadata, tags, owner_email, notes, certificate_fingerprint,
                           capabilities
                    FROM registered_devices 
                    ORDER BY registration_time DESC
                    """
                )
                
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
                        metadata=json.loads(row[8]) if row[8] else {},
                        tags=json.loads(row[9]) if row[9] else [],
                        owner_email=row[10] or "",
                        notes=row[11] or "",
                        certificate_fingerprint=row[12] or "",
                        capabilities=json.loads(row[13]) if row[13] else []
                    )
                    devices.append(device)
                
                return devices
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка устройств: {e}")
            return []

    def get_device(self, device_id: str) -> Optional[RegisteredDevice]:
        """Получение информации об устройстве по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT device_id, hostname, tailscale_ip, auth_key_hash,
                           registration_time, last_seen, status, device_type,
                           metadata, tags, owner_email, notes, certificate_fingerprint,
                           capabilities
                    FROM registered_devices 
                    WHERE device_id = ?
                    """,
                    (device_id,)
                )
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                device = RegisteredDevice(
                    device_id=row[0],
                    hostname=row[1],
                    tailscale_ip=row[2],
                    auth_key_hash=row[3],
                    registration_time=row[4],
                    last_seen=row[5],
                    status=row[6],
                    device_type=row[7],
                    metadata=json.loads(row[8]) if row[8] else {},
                    tags=json.loads(row[9]) if row[9] else [],
                    owner_email=row[10] or "",
                    notes=row[11] or "",
                    certificate_fingerprint=row[12] or "",
                    capabilities=json.loads(row[13]) if row[13] else []
                )
                
                return device
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения устройства {device_id}: {e}")
            return None

    def get_pending_requests(self) -> List[DeviceRegistrationRequest]:
        """Получение ожидающих запросов на регистрацию"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT request_id, auth_key_hash, device_hostname, device_type,
                           device_info, requested_time, tailscale_ip, status,
                           approved_by, approved_time, certificate_fingerprint, capabilities
                    FROM registration_requests 
                    WHERE status = 'pending'
                    ORDER BY requested_time DESC
                    """
                )
                
                requests = []
                for row in cursor.fetchall():
                    request = DeviceRegistrationRequest(
                        request_id=row[0],
                        auth_key_hash=row[1],
                        device_hostname=row[2],
                        device_type=row[3],
                        device_info=json.loads(row[4]) if row[4] else {},
                        requested_time=row[5],
                        tailscale_ip=row[6],
                        status=row[7],
                        approved_by=row[8] or "",
                        approved_time=row[9] or "",
                        certificate_fingerprint=row[10] or "",
                        capabilities=json.loads(row[11]) if row[11] else []
                    )
                    requests.append(request)
                
                return requests
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения ожидающих запросов: {e}")
            return []

    def update_device_last_seen(self, device_id: str) -> bool:
        """Обновление времени последнего обращения устройства"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE registered_devices SET last_seen = ? WHERE device_id = ?",
                    (datetime.now().isoformat(), device_id)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.debug(f"📡 Обновлено время последнего обращения для {device_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Устройство {device_id} не найдено для обновления last_seen")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обновления last_seen для {device_id}: {e}")
            return False

    def revoke_device(self, device_id: str) -> bool:
        """Отзыв устройства"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE registered_devices SET status = 'revoked' WHERE device_id = ?",
                    (device_id,)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"❌ Устройство {device_id} отозвано")
                    return True
                else:
                    logger.warning(f"⚠️ Устройство {device_id} не найдено для отзыва")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка отзыва устройства {device_id}: {e}")
            return False

    def get_statistics(self) -> dict:
        """Получение статистики регистрации устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Общая статистика устройств
                cursor.execute("SELECT status, COUNT(*) FROM registered_devices GROUP BY status")
                device_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Статистика по типам устройств
                cursor.execute("SELECT device_type, COUNT(*) FROM registered_devices GROUP BY device_type")
                device_type_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Статистика запросов на регистрацию
                cursor.execute("SELECT status, COUNT(*) FROM registration_requests GROUP BY status")
                request_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Статистика ключей авторизации
                cursor.execute("SELECT status, COUNT(*) FROM auth_keys GROUP BY status")
                key_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {
                    "devices": device_stats,
                    "device_types": device_type_stats,
                    "registration_requests": request_stats,
                    "auth_keys": key_stats,
                    "total_devices": sum(device_stats.values()),
                    "total_requests": sum(request_stats.values()),
                    "total_keys": sum(key_stats.values())
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}


# Глобальный экземпляр реестра устройств
_device_registry = None


def get_device_registry(db_path: str = "device_registry.db") -> DeviceRegistry:
    """Получение глобального экземпляра реестра устройств (Singleton)"""
    global _device_registry
    if _device_registry is None:
        _device_registry = DeviceRegistry(db_path)
    return _device_registry


if __name__ == "__main__":
    # Пример использования Device Registry
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )
    
    registry = DeviceRegistry("test_device_registry.db")
    
    # Создаем ключ авторизации
    key_id, auth_key = registry.create_auth_key(
        device_types=["farm", "edge"],
        max_usage=10,
        expires_in_hours=24*7,  # Неделя
        tags=["test", "demo"]
    )
    
    print(f"🔑 Создан ключ: {key_id}")
    print(f"   Auth Key: {auth_key}")
    
    # Регистрируем устройство
    request_id = registry.register_device_request(
        auth_key=auth_key,
        hostname="test-farm-01",
        device_type="farm",
        device_info={"os": "linux", "version": "1.0"},
        capabilities=["kub1063", "monitoring"]
    )
    
    print(f"📝 Создан запрос: {request_id}")
    
    # Одобряем регистрацию
    if registry.approve_device_registration(request_id, "test_admin"):
        print("✅ Устройство одобрено и зарегистрировано")
    
    # Показываем статистику
    stats = registry.get_statistics()
    print(f"📊 Статистика: {json.dumps(stats, indent=2, ensure_ascii=False)}")
    
    # Показываем все устройства
    devices = registry.get_all_devices()
    print(f"🔍 Всего устройств: {len(devices)}")
    for device in devices:
        print(f"   - {device.hostname} ({device.device_type}): {device.status}")