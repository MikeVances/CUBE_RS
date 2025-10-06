#!/usr/bin/env python3
"""
RBAC System - Role-Based Access Control для управления доступом к Tailscale устройствам
Основано на принципах IXON Cloud ролевой модели
Ported from archive to SERVER for centralized access control
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Базовые разрешения системы"""

    # Device permissions
    DEVICE_VIEW = "device:view"
    DEVICE_CONNECT = "device:connect"
    DEVICE_CONFIGURE = "device:configure"
    DEVICE_MANAGE = "device:manage"
    DEVICE_DELETE = "device:delete"

    # Service permissions
    VPN_ACCESS = "service:vpn"
    VNC_ACCESS = "service:vnc"
    HTTP_ACCESS = "service:http"
    SSH_ACCESS = "service:ssh"
    API_ACCESS = "service:api"
    MODBUS_ACCESS = "service:modbus"
    TUNNEL_ACCESS = "service:tunnel"

    # Data permissions
    DATA_VIEW = "data:view"
    DATA_EXPORT = "data:export"
    DATA_MANAGE = "data:manage"
    HISTORY_VIEW = "data:history"
    STATISTICS_VIEW = "data:statistics"

    # Administrative permissions
    USER_MANAGE = "admin:users"
    ROLE_MANAGE = "admin:roles"
    DEVICE_REGISTER = "admin:device_register"
    SYSTEM_CONFIGURE = "admin:system"
    AUDIT_VIEW = "admin:audit"
    SECURITY_MANAGE = "admin:security"


@dataclass
class Role:
    """Роль пользователя"""

    role_id: str
    name: str
    description: str
    permissions: list[str]
    is_system_role: bool = False
    created_time: str = ""
    created_by: str = "system"
    device_restrictions: dict[str, Any] = None  # Ограничения по устройствам

    def __post_init__(self):
        if self.device_restrictions is None:
            self.device_restrictions = {}

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def can_access_device_type(self, device_type: str) -> bool:
        """Проверка доступа к типу устройства"""
        allowed_types = self.device_restrictions.get("device_types", [])
        if not allowed_types:  # Нет ограничений - разрешен доступ
            return True
        return device_type in allowed_types


@dataclass
class User:
    """Пользователь системы"""

    user_id: str
    username: str
    email: str
    full_name: str
    password_hash: str
    is_active: bool = True
    is_admin: bool = False
    roles: list[str] = None  # role_ids
    device_groups: list[str] = None  # device_group_ids
    metadata: dict[str, Any] = None
    created_time: str = ""
    last_login: str = ""
    session_token: str = ""  # Для сессии
    session_expires: str = ""  # Когда истекает сессия

    def __post_init__(self):
        if self.roles is None:
            self.roles = []
        if self.device_groups is None:
            self.device_groups = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DeviceGroup:
    """Группа устройств для управления доступом"""

    group_id: str
    name: str
    description: str
    device_ids: list[str]
    device_types: list[str]  # Автоматическое включение по типу
    tags_filter: list[str]  # Автоматическое включение по тегам
    parent_group_id: str = ""
    metadata: dict[str, Any] = None
    created_time: str = ""
    owner_id: str = ""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RBACSystem:
    """Система управления доступом на основе ролей"""

    def __init__(self, db_path: str = "rbac_system.db"):
        self.db_path = db_path
        self.init_database()
        self._init_default_roles()
        logger.info(f"🔐 RBAC System инициализирован: {db_path}")

    def init_database(self):
        """Инициализация базы данных RBAC"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица ролей
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS roles (
                        role_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        permissions TEXT NOT NULL,
                        is_system_role BOOLEAN DEFAULT FALSE,
                        created_time TEXT,
                        created_by TEXT,
                        device_restrictions TEXT
                    )
                    """
                )
                
                # Таблица пользователей
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        full_name TEXT,
                        password_hash TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_admin BOOLEAN DEFAULT FALSE,
                        roles TEXT,
                        device_groups TEXT,
                        metadata TEXT,
                        created_time TEXT,
                        last_login TEXT,
                        session_token TEXT,
                        session_expires TEXT
                    )
                    """
                )
                
                # Таблица групп устройств
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_groups (
                        group_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        device_ids TEXT,
                        device_types TEXT,
                        tags_filter TEXT,
                        parent_group_id TEXT,
                        metadata TEXT,
                        created_time TEXT,
                        owner_id TEXT
                    )
                    """
                )
                
                # Таблица аудита
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        action TEXT NOT NULL,
                        resource_type TEXT,
                        resource_id TEXT,
                        details TEXT,
                        ip_address TEXT,
                        user_agent TEXT,
                        timestamp TEXT NOT NULL,
                        result TEXT
                    )
                    """
                )
                
                # Индексы
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_session ON users(session_token)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
                
                conn.commit()
                logger.info("✅ База данных RBAC инициализирована")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных RBAC: {e}")
            raise

    def _init_default_roles(self):
        """Создание системных ролей по умолчанию"""
        default_roles = [
            Role(
                role_id="admin",
                name="Administrator",
                description="Full system administrator with all permissions",
                permissions=[
                    perm.value for perm in Permission
                ],  # Все разрешения
                is_system_role=True,
                created_time=datetime.now().isoformat(),
            ),
            Role(
                role_id="farm_operator",
                name="Farm Operator",
                description="Can monitor and control farm devices",
                permissions=[
                    Permission.DEVICE_VIEW.value,
                    Permission.DEVICE_CONNECT.value,
                    Permission.DEVICE_CONFIGURE.value,
                    Permission.DATA_VIEW.value,
                    Permission.DATA_EXPORT.value,
                    Permission.HISTORY_VIEW.value,
                    Permission.STATISTICS_VIEW.value,
                    Permission.HTTP_ACCESS.value,
                    Permission.API_ACCESS.value,
                    Permission.MODBUS_ACCESS.value,
                ],
                is_system_role=True,
                created_time=datetime.now().isoformat(),
                device_restrictions={"device_types": ["farm", "edge"]},
            ),
            Role(
                role_id="viewer",
                name="Viewer",
                description="Read-only access to devices and data",
                permissions=[
                    Permission.DEVICE_VIEW.value,
                    Permission.DATA_VIEW.value,
                    Permission.HISTORY_VIEW.value,
                    Permission.STATISTICS_VIEW.value,
                    Permission.HTTP_ACCESS.value,
                ],
                is_system_role=True,
                created_time=datetime.now().isoformat(),
            ),
            Role(
                role_id="mobile_user",
                name="Mobile User",
                description="Mobile app user with limited permissions",
                permissions=[
                    Permission.DEVICE_VIEW.value,
                    Permission.DATA_VIEW.value,
                    Permission.TUNNEL_ACCESS.value,
                    Permission.API_ACCESS.value,
                ],
                is_system_role=True,
                created_time=datetime.now().isoformat(),
                device_restrictions={"device_types": ["farm"]},
            ),
        ]
        
        for role in default_roles:
            if not self.get_role(role.role_id):
                self.create_role(role)
                logger.info(f"🎩 Создана системная роль: {role.name}")

    def create_role(self, role: Role) -> bool:
        """Создание новой роли"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO roles (
                        role_id, name, description, permissions, is_system_role,
                        created_time, created_by, device_restrictions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        role.role_id,
                        role.name,
                        role.description,
                        json.dumps(role.permissions),
                        role.is_system_role,
                        role.created_time or datetime.now().isoformat(),
                        role.created_by,
                        json.dumps(role.device_restrictions),
                    ),
                )
                conn.commit()
            
            logger.info(f"✅ Роль {role.name} создана")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания роли {role.role_id}: {e}")
            return False

    def get_role(self, role_id: str) -> Optional[Role]:
        """Получение роли по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role_id, name, description, permissions, is_system_role,
                           created_time, created_by, device_restrictions
                    FROM roles WHERE role_id = ?
                    """,
                    (role_id,),
                )
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                role = Role(
                    role_id=row[0],
                    name=row[1],
                    description=row[2],
                    permissions=json.loads(row[3]) if row[3] else [],
                    is_system_role=bool(row[4]),
                    created_time=row[5],
                    created_by=row[6],
                    device_restrictions=json.loads(row[7]) if row[7] else {},
                )
                
                return role
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения роли {role_id}: {e}")
            return None

    def create_user(
        self, 
        username: str, 
        email: str, 
        password: str, 
        full_name: str = "", 
        roles: list[str] = None,
        is_admin: bool = False
    ) -> Optional[str]:
        """Создание нового пользователя"""
        try:
            user_id = secrets.token_urlsafe(16)
            password_hash = self._hash_password(password)
            
            if roles is None:
                roles = ["viewer"]  # По умолчанию роль viewer
            
            user = User(
                user_id=user_id,
                username=username,
                email=email,
                full_name=full_name,
                password_hash=password_hash,
                is_admin=is_admin,
                roles=roles,
                created_time=datetime.now().isoformat(),
            )
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (
                        user_id, username, email, full_name, password_hash,
                        is_active, is_admin, roles, device_groups, metadata,
                        created_time, last_login, session_token, session_expires
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.user_id,
                        user.username,
                        user.email,
                        user.full_name,
                        user.password_hash,
                        user.is_active,
                        user.is_admin,
                        json.dumps(user.roles),
                        json.dumps(user.device_groups),
                        json.dumps(user.metadata),
                        user.created_time,
                        user.last_login,
                        user.session_token,
                        user.session_expires,
                    ),
                )
                conn.commit()
            
            self._log_audit(user_id, "USER_CREATE", "user", user_id, {"username": username})
            logger.info(f"✅ Пользователь {username} создан")
            return user_id
            
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                logger.error(f"❌ Пользователь с именем {username} уже существует")
            elif "email" in str(e):
                logger.error(f"❌ Пользователь с email {email} уже существует")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка создания пользователя: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Аутентификация пользователя"""
        try:
            user = self.get_user_by_username(username)
            if not user:
                logger.warning(f"⚠️ Пользователь {username} не найден")
                return None
            
            if not user.is_active:
                logger.warning(f"⚠️ Пользователь {username} неактивен")
                return None
            
            if not self._verify_password(password, user.password_hash):
                logger.warning(f"⚠️ Неверный пароль для пользователя {username}")
                self._log_audit(user.user_id, "LOGIN_FAILED", "auth", user.user_id, {"reason": "invalid_password"})
                return None
            
            # Обновляем время последнего входа
            self._update_last_login(user.user_id)
            self._log_audit(user.user_id, "LOGIN_SUCCESS", "auth", user.user_id)
            
            logger.info(f"✅ Успешная аутентификация пользователя {username}")
            return user
            
        except Exception as e:
            logger.error(f"❌ Ошибка аутентификации: {e}")
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Получение пользователя по имени"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, email, full_name, password_hash,
                           is_active, is_admin, roles, device_groups, metadata,
                           created_time, last_login, session_token, session_expires
                    FROM users WHERE username = ?
                    """,
                    (username,),
                )
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                user = User(
                    user_id=row[0],
                    username=row[1],
                    email=row[2],
                    full_name=row[3],
                    password_hash=row[4],
                    is_active=bool(row[5]),
                    is_admin=bool(row[6]),
                    roles=json.loads(row[7]) if row[7] else [],
                    device_groups=json.loads(row[8]) if row[8] else [],
                    metadata=json.loads(row[9]) if row[9] else {},
                    created_time=row[10],
                    last_login=row[11],
                    session_token=row[12],
                    session_expires=row[13],
                )
                
                return user
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователя {username}: {e}")
            return None

    def user_has_permission(self, user_id: str, permission: str) -> bool:
        """Проверка разрешения пользователя"""
        try:
            user = self.get_user(user_id)
            if not user or not user.is_active:
                return False
            
            # Администратор имеет все разрешения
            if user.is_admin:
                return True
            
            # Проверяем роли пользователя
            for role_id in user.roles:
                role = self.get_role(role_id)
                if role and role.has_permission(permission):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки разрешения: {e}")
            return False

    def get_user(self, user_id: str) -> Optional[User]:
        """Получение пользователя по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, email, full_name, password_hash,
                           is_active, is_admin, roles, device_groups, metadata,
                           created_time, last_login, session_token, session_expires
                    FROM users WHERE user_id = ?
                    """,
                    (user_id,),
                )
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                user = User(
                    user_id=row[0],
                    username=row[1],
                    email=row[2],
                    full_name=row[3],
                    password_hash=row[4],
                    is_active=bool(row[5]),
                    is_admin=bool(row[6]),
                    roles=json.loads(row[7]) if row[7] else [],
                    device_groups=json.loads(row[8]) if row[8] else [],
                    metadata=json.loads(row[9]) if row[9] else {},
                    created_time=row[10],
                    last_login=row[11],
                    session_token=row[12],
                    session_expires=row[13],
                )
                
                return user
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователя {user_id}: {e}")
            return None

    def get_all_users(self) -> List[User]:
        """Получение списка всех пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, email, full_name, password_hash,
                           is_active, is_admin, roles, device_groups, metadata,
                           created_time, last_login, session_token, session_expires
                    FROM users ORDER BY created_time DESC
                    """
                )
                
                users = []
                for row in cursor.fetchall():
                    user = User(
                        user_id=row[0],
                        username=row[1],
                        email=row[2],
                        full_name=row[3],
                        password_hash=row[4],
                        is_active=bool(row[5]),
                        is_admin=bool(row[6]),
                        roles=json.loads(row[7]) if row[7] else [],
                        device_groups=json.loads(row[8]) if row[8] else [],
                        metadata=json.loads(row[9]) if row[9] else {},
                        created_time=row[10],
                        last_login=row[11],
                        session_token=row[12],
                        session_expires=row[13],
                    )
                    users.append(user)
                
                return users
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка пользователей: {e}")
            return []

    def get_all_roles(self) -> List[Role]:
        """Получение списка всех ролей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role_id, name, description, permissions, is_system_role,
                           created_time, created_by, device_restrictions
                    FROM roles ORDER BY created_time
                    """
                )
                
                roles = []
                for row in cursor.fetchall():
                    role = Role(
                        role_id=row[0],
                        name=row[1],
                        description=row[2],
                        permissions=json.loads(row[3]) if row[3] else [],
                        is_system_role=bool(row[4]),
                        created_time=row[5],
                        created_by=row[6],
                        device_restrictions=json.loads(row[7]) if row[7] else {},
                    )
                    roles.append(role)
                
                return roles
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка ролей: {e}")
            return []

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля"""
        # Простое хеширование SHA-256 (в продакшене стоит использовать bcrypt или argon2)
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Проверка пароля"""
        try:
            salt, hash_value = stored_hash.split(":")
            password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return hash_value == password_hash
        except:
            return False

    def _update_last_login(self, user_id: str):
        """Обновление времени последнего входа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET last_login = ? WHERE user_id = ?",
                    (datetime.now().isoformat(), user_id),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления last_login: {e}")

    def _log_audit(self, user_id: str, action: str, resource_type: str, resource_id: str, details: dict = None, result: str = "success"):
        """Запись аудита"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO audit_log (
                        user_id, action, resource_type, resource_id, details,
                        ip_address, user_agent, timestamp, result
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        action,
                        resource_type,
                        resource_id,
                        json.dumps(details) if details else None,
                        "",  # IP address - можно добавить через Flask request
                        "",  # User agent - можно добавить через Flask request
                        datetime.now().isoformat(),
                        result,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка записи аудита: {e}")

    def get_audit_log(self, user_id: str = None, limit: int = 100) -> List[dict]:
        """Получение журнала аудита"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if user_id:
                    cursor.execute(
                        """
                        SELECT id, user_id, action, resource_type, resource_id,
                               details, ip_address, user_agent, timestamp, result
                        FROM audit_log WHERE user_id = ?
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (user_id, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, user_id, action, resource_type, resource_id,
                               details, ip_address, user_agent, timestamp, result
                        FROM audit_log
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (limit,),
                    )
                
                audit_entries = []
                for row in cursor.fetchall():
                    entry = {
                        "id": row[0],
                        "user_id": row[1],
                        "action": row[2],
                        "resource_type": row[3],
                        "resource_id": row[4],
                        "details": json.loads(row[5]) if row[5] else {},
                        "ip_address": row[6],
                        "user_agent": row[7],
                        "timestamp": row[8],
                        "result": row[9],
                    }
                    audit_entries.append(entry)
                
                return audit_entries
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения аудита: {e}")
            return []

    def get_statistics(self) -> dict:
        """Получение статистики RBAC системы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Общая статистика
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
                active_users = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
                admin_users = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM roles")
                total_roles = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM audit_log")
                audit_entries = cursor.fetchone()[0]
                
                # Статистика по ролям
                cursor.execute(
                    """
                    SELECT r.name, COUNT(u.user_id) as user_count
                    FROM roles r
                    LEFT JOIN users u ON JSON_EXTRACT(u.roles, '$') LIKE '%' || r.role_id || '%'
                    WHERE u.is_active = 1 OR u.user_id IS NULL
                    GROUP BY r.role_id, r.name
                    ORDER BY user_count DESC
                    """
                )
                role_usage = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {
                    "active_users": active_users,
                    "admin_users": admin_users,
                    "total_roles": total_roles,
                    "audit_entries": audit_entries,
                    "role_usage": role_usage,
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики RBAC: {e}")
            return {}


if __name__ == "__main__":
    # Пример использования RBAC системы
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
    )
    
    rbac = RBACSystem("test_rbac.db")
    
    # Создаем тестового пользователя
    user_id = rbac.create_user(
        username="test_user",
        email="test@example.com",
        password="test_password",
        full_name="Test User",
        roles=["farm_operator"]
    )
    
    if user_id:
        print(f"✅ Создан пользователь: {user_id}")
        
        # Аутентификация
        user = rbac.authenticate_user("test_user", "test_password")
        if user:
            print(f"✅ Аутентификация успешна: {user.username}")
            
            # Проверка разрешений
            has_view = rbac.user_has_permission(user.user_id, Permission.DEVICE_VIEW.value)
            has_delete = rbac.user_has_permission(user.user_id, Permission.DEVICE_DELETE.value)
            
            print(f"   - Может просматривать устройства: {has_view}")
            print(f"   - Может удалять устройства: {has_delete}")
        
        # Показываем статистику
        stats = rbac.get_statistics()
        print(f"📊 Статистика RBAC: {json.dumps(stats, indent=2, ensure_ascii=False)}")
        
        # Показываем все роли
        roles = rbac.get_all_roles()
        print(f"🎩 Всего ролей: {len(roles)}")
        for role in roles:
            print(f"   - {role.name}: {len(role.permissions)} permissions")