#!/usr/bin/env python3
"""
Система аутентификации и управления ключами для EDGE SERVER
Обеспечивает безопасное подключение EDGE устройств и пользователей APP с защитой от MITM атак
"""

import hashlib
import hmac
import secrets
import time
import sqlite3
import jwt
import os
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Импортируем MITM защиту для SERVER
from .security import CertificateAuthority, setup_device_mtls

# Импортируем мониторинг безопасности
from .monitoring import SecurityMonitor, SecurityEvent

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """Роли пользователей"""
    ADMIN = "admin"          # Полные права
    FARM_OWNER = "farm_owner" # Владелец ферм
    VIEWER = "viewer"        # Только просмотр
    EDGE_DEVICE = "edge_device" # EDGE устройство


@dataclass
class APIKey:
    """API ключ для аутентификации"""
    key_id: str
    key_hash: str
    owner_id: str
    role: UserRole
    name: str
    permissions: List[str]
    created_at: float
    expires_at: Optional[float] = None
    last_used: Optional[float] = None
    is_active: bool = True


@dataclass
class AuthToken:
    """Токен аутентификации"""
    token: str
    user_id: str
    role: UserRole
    permissions: List[str]
    issued_at: float
    expires_at: float


class AuthenticationManager:
    """Менеджер аутентификации и авторизации"""
    
    def __init__(self, db_path: str = "auth.db", jwt_secret: str = None):
        self.db_path = db_path
        self.jwt_secret = jwt_secret or os.getenv('JWT_SECRET') or secrets.token_hex(32)
        self.init_database()
        
        # Время жизни токенов
        self.token_lifetime = {
            UserRole.ADMIN: 3600 * 8,        # 8 часов
            UserRole.FARM_OWNER: 3600 * 24,  # 24 часа  
            UserRole.VIEWER: 3600 * 12,      # 12 часов
            UserRole.EDGE_DEVICE: 3600 * 24 * 30  # 30 дней
        }
    
    def init_database(self):
        """Инициализация базы данных аутентификации"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    permissions TEXT,  -- JSON array
                    created_at REAL NOT NULL,
                    last_login REAL,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT      -- JSON для дополнительных данных
                )
            """)
            
            # Таблица API ключей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    name TEXT NOT NULL,
                    permissions TEXT,  -- JSON array
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    last_used REAL,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    FOREIGN KEY (owner_id) REFERENCES users (user_id)
                )
            """)
            
            # Таблица сессий
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_activity REAL,
                    ip_address TEXT,
                    user_agent TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # Таблица EDGE устройств
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS edge_devices (
                    device_id TEXT PRIMARY KEY,
                    farm_id TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    api_key_id TEXT,
                    device_type TEXT,
                    firmware_version TEXT,
                    last_heartbeat REAL,
                    ip_address TEXT,
                    status TEXT DEFAULT 'offline',
                    capabilities TEXT, -- JSON array
                    metadata TEXT,     -- JSON для дополнительных данных
                    created_at REAL NOT NULL,
                    FOREIGN KEY (owner_id) REFERENCES users (user_id),
                    FOREIGN KEY (api_key_id) REFERENCES api_keys (key_id)
                )
            """)
            
            conn.commit()
            logger.info("✅ Auth database initialized")
    
    def create_user(self, username: str, password: str, role: UserRole, 
                   email: str = None, permissions: List[str] = None) -> str:
        """Создание нового пользователя"""
        user_id = f"user_{secrets.token_hex(8)}"
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users 
                (user_id, username, email, password_hash, role, permissions, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, username, email, password_hash, role.value,
                ','.join(permissions) if permissions else None,
                time.time()
            ))
            conn.commit()
        
        logger.info(f"✅ User created: {username} ({role.value})")
        return user_id
    
    def authenticate_user(self, username: str, password: str) -> Optional[AuthToken]:
        """Аутентификация пользователя по логину/паролю"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, role, permissions, is_active 
                FROM users 
                WHERE username = ? AND password_hash = ?
            """, (username, password_hash))
            
            result = cursor.fetchone()
            if not result or not result[3]:  # is_active
                return None
            
            user_id, role, permissions, _ = result
            role_enum = UserRole(role)
            perm_list = permissions.split(',') if permissions else []
            
            # Обновляем last_login
            cursor.execute("""
                UPDATE users SET last_login = ? WHERE user_id = ?
            """, (time.time(), user_id))
            conn.commit()
        
        # Генерируем JWT токен
        token = self._generate_jwt_token(user_id, role_enum, perm_list)
        
        return AuthToken(
            token=token,
            user_id=user_id,
            role=role_enum,
            permissions=perm_list,
            issued_at=time.time(),
            expires_at=time.time() + self.token_lifetime[role_enum]
        )
    
    def create_api_key(self, owner_id: str, name: str, role: UserRole,
                      permissions: List[str] = None, expires_in_days: int = None) -> Tuple[str, str]:
        """Создание API ключа для EDGE устройства или приложения"""
        key_id = f"key_{secrets.token_hex(8)}"
        api_key = f"edge_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        expires_at = None
        if expires_in_days:
            expires_at = time.time() + (expires_in_days * 24 * 3600)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys 
                (key_id, key_hash, owner_id, role, name, permissions, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key_id, key_hash, owner_id, role.value, name,
                ','.join(permissions) if permissions else None,
                time.time(), expires_at
            ))
            conn.commit()
        
        logger.info(f"✅ API key created: {name} for {owner_id}")
        return key_id, api_key
    
    def authenticate_api_key(self, api_key: str) -> Optional[AuthToken]:
        """Аутентификация по API ключу"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        current_time = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key_id, owner_id, role, permissions, expires_at, is_active
                FROM api_keys 
                WHERE key_hash = ? AND is_active = 1
            """, (key_hash,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            key_id, owner_id, role, permissions, expires_at, is_active = result
            
            # Проверяем срок действия
            if expires_at and expires_at < current_time:
                return None
            
            # Обновляем last_used
            cursor.execute("""
                UPDATE api_keys SET last_used = ? WHERE key_id = ?
            """, (current_time, key_id))
            conn.commit()
        
        role_enum = UserRole(role)
        perm_list = permissions.split(',') if permissions else []
        
        return AuthToken(
            token=api_key,
            user_id=owner_id,
            role=role_enum,
            permissions=perm_list,
            issued_at=current_time,
            expires_at=expires_at or (current_time + self.token_lifetime[role_enum])
        )
    
    def register_edge_device(self, farm_id: str, device_name: str, owner_id: str,
                           device_type: str = "EDGE", capabilities: List[str] = None) -> Tuple[str, str]:
        """Регистрация EDGE устройства и создание API ключа"""
        device_id = f"edge_{secrets.token_hex(6)}"
        
        # Создаем API ключ для устройства
        key_id, api_key = self.create_api_key(
            owner_id=owner_id,
            name=f"EDGE-{device_name}",
            role=UserRole.EDGE_DEVICE,
            permissions=["device:heartbeat", "device:data", "tunnel:connect"],
            expires_in_days=365  # Год
        )
        
        # Регистрируем устройство
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO edge_devices 
                (device_id, farm_id, device_name, owner_id, api_key_id, device_type, 
                 capabilities, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, farm_id, device_name, owner_id, key_id, device_type,
                ','.join(capabilities) if capabilities else None,
                time.time()
            ))
            conn.commit()
        
        logger.info(f"✅ EDGE device registered: {device_name} ({device_id})")
        return device_id, api_key
    
    def validate_token(self, token: str) -> Optional[AuthToken]:
        """Валидация JWT токена"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            
            # Проверяем срок действия
            if payload['exp'] < time.time():
                return None
            
            return AuthToken(
                token=token,
                user_id=payload['user_id'],
                role=UserRole(payload['role']),
                permissions=payload.get('permissions', []),
                issued_at=payload['iat'],
                expires_at=payload['exp']
            )
        except jwt.InvalidTokenError:
            return None
    
    def check_permission(self, token: AuthToken, required_permission: str) -> bool:
        """Проверка разрешения пользователя"""
        # Админы могут всё
        if token.role == UserRole.ADMIN:
            return True
        
        # Проверяем конкретное разрешение
        return required_permission in token.permissions
    
    def revoke_api_key(self, key_id: str) -> bool:
        """Отзыв API ключа"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys SET is_active = 0 WHERE key_id = ?
            """, (key_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def list_user_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """Список API ключей пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key_id, name, role, created_at, expires_at, last_used, is_active
                FROM api_keys 
                WHERE owner_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            
            keys = []
            for row in cursor.fetchall():
                keys.append({
                    'key_id': row[0],
                    'name': row[1],
                    'role': row[2],
                    'created_at': row[3],
                    'expires_at': row[4],
                    'last_used': row[5],
                    'is_active': bool(row[6])
                })
            
            return keys
    
    def list_edge_devices(self, owner_id: str = None) -> List[Dict[str, Any]]:
        """Список EDGE устройств"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if owner_id:
                cursor.execute("""
                    SELECT device_id, farm_id, device_name, device_type, 
                           last_heartbeat, status, capabilities
                    FROM edge_devices 
                    WHERE owner_id = ?
                    ORDER BY last_heartbeat DESC
                """, (owner_id,))
            else:
                cursor.execute("""
                    SELECT device_id, farm_id, device_name, device_type,
                           last_heartbeat, status, capabilities, owner_id
                    FROM edge_devices 
                    ORDER BY last_heartbeat DESC
                """)
            
            devices = []
            for row in cursor.fetchall():
                device = {
                    'device_id': row[0],
                    'farm_id': row[1],
                    'device_name': row[2],
                    'device_type': row[3],
                    'last_heartbeat': row[4],
                    'status': row[5],
                    'capabilities': row[6].split(',') if row[6] else []
                }
                if not owner_id:
                    device['owner_id'] = row[7]
                
                devices.append(device)
            
            return devices
    
    def update_device_heartbeat(self, device_id: str, ip_address: str = None):
        """Обновление heartbeat устройства"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE edge_devices 
                SET last_heartbeat = ?, status = 'online', ip_address = ?
                WHERE device_id = ?
            """, (time.time(), ip_address, device_id))
            conn.commit()
    
    def _generate_jwt_token(self, user_id: str, role: UserRole, permissions: List[str]) -> str:
        """Генерация JWT токена"""
        current_time = time.time()
        payload = {
            'user_id': user_id,
            'role': role.value,
            'permissions': permissions,
            'iat': current_time,
            'exp': current_time + self.token_lifetime[role]
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')


def require_auth(required_permission: str = None):
    """Декоратор для проверки аутентификации"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Здесь будет логика проверки токена из запроса
            # Интеграция с Flask/FastAPI
            pass
        return wrapper
    return decorator


# Глобальный экземпляр менеджера аутентификации
_auth_manager: Optional[AuthenticationManager] = None


def get_auth_manager() -> AuthenticationManager:
    """Получение глобального экземпляра менеджера аутентификации"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthenticationManager()
    return _auth_manager


if __name__ == "__main__":
    # Тестовый запуск
    logging.basicConfig(level=logging.INFO)
    
    auth = AuthenticationManager("test_auth.db")
    
    # Создаем администратора
    admin_id = auth.create_user(
        username="admin",
        password="admin123",
        role=UserRole.ADMIN,
        email="admin@edge-system.com",
        permissions=["*"]
    )
    
    # Создаем владельца фермы
    owner_id = auth.create_user(
        username="farmer1",
        password="farmer123",
        role=UserRole.FARM_OWNER,
        email="farmer@example.com",
        permissions=["farm:view", "farm:manage", "device:view"]
    )
    
    # Регистрируем EDGE устройство
    device_id, api_key = auth.register_edge_device(
        farm_id="farm_001",
        device_name="EDGE-Корпус-1",
        owner_id=owner_id,
        device_type="KUB-EDGE",
        capabilities=["kub1063", "kub1112", "tunnel"]
    )
    
    print(f"✅ EDGE device registered: {device_id}")
    print(f"🔑 API key: {api_key}")
    
    # Тестируем аутентификацию
    token = auth.authenticate_user("farmer1", "farmer123")
    if token:
        print(f"✅ User authenticated: {token.user_id}")
        print(f"🎭 Role: {token.role}")
        print(f"🔐 Permissions: {token.permissions}")
    
    # Тестируем API ключ
    api_token = auth.authenticate_api_key(api_key)
    if api_token:
        print(f"✅ API key valid: {api_token.user_id}")
        print(f"🎭 Role: {api_token.role}")