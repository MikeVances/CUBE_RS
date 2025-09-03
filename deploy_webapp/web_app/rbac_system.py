#!/usr/bin/env python3
"""
RBAC System - Role-Based Access Control для управления доступом к Tailscale устройствам
Основано на принципах IXON Cloud ролевой модели
"""

import sqlite3
import json
import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import os

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
    
    # Administrative permissions
    USER_MANAGE = "admin:users"
    ROLE_MANAGE = "admin:roles"
    DEVICE_REGISTER = "admin:device_register"
    SYSTEM_CONFIGURE = "admin:system"
    AUDIT_VIEW = "admin:audit"

@dataclass
class Role:
    """Роль пользователя"""
    role_id: str
    name: str
    description: str
    permissions: List[str]
    is_system_role: bool = False
    created_time: str = ""
    created_by: str = "system"
    
    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

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
    roles: List[str] = None  # role_ids
    device_groups: List[str] = None  # device_group_ids
    metadata: Dict[str, Any] = None
    created_time: str = ""
    last_login: str = ""
    
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
    device_ids: List[str]
    device_types: List[str]  # Автоматическое включение по типу
    tags_filter: List[str]   # Автоматическое включение по тегам
    parent_group_id: str = ""
    metadata: Dict[str, Any] = None
    created_time: str = ""
    created_by: str = "system"
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class AccessPolicy:
    """Политика доступа к группе устройств"""
    policy_id: str
    name: str
    description: str
    device_group_id: str
    role_id: str
    permissions: List[str]
    time_restrictions: Dict[str, Any] = None  # Временные ограничения
    ip_restrictions: List[str] = None         # IP ограничения
    is_active: bool = True
    created_time: str = ""
    created_by: str = "system"
    
    def __post_init__(self):
        if self.time_restrictions is None:
            self.time_restrictions = {}
        if self.ip_restrictions is None:
            self.ip_restrictions = []

class RBACSystem:
    """Система управления ролями и доступом"""
    
    def __init__(self, db_path: str = "rbac_system.db"):
        self.db_path = db_path
        self.init_database()
        self.create_default_roles()
    
    def init_database(self):
        """Инициализация базы данных RBAC"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Таблица ролей
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS roles (
                        role_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        permissions TEXT NOT NULL,
                        is_system_role BOOLEAN DEFAULT 0,
                        created_time TEXT NOT NULL,
                        created_by TEXT DEFAULT 'system',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица пользователей
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        email TEXT NOT NULL UNIQUE,
                        full_name TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT 1,
                        is_admin BOOLEAN DEFAULT 0,
                        roles TEXT DEFAULT '[]',
                        device_groups TEXT DEFAULT '[]',
                        metadata TEXT DEFAULT '{}',
                        created_time TEXT NOT NULL,
                        last_login TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица групп устройств
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS device_groups (
                        group_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        device_ids TEXT DEFAULT '[]',
                        device_types TEXT DEFAULT '[]',
                        tags_filter TEXT DEFAULT '[]',
                        parent_group_id TEXT DEFAULT '',
                        metadata TEXT DEFAULT '{}',
                        created_time TEXT NOT NULL,
                        created_by TEXT DEFAULT 'system',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица политик доступа
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS access_policies (
                        policy_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        device_group_id TEXT NOT NULL,
                        role_id TEXT NOT NULL,
                        permissions TEXT NOT NULL,
                        time_restrictions TEXT DEFAULT '{}',
                        ip_restrictions TEXT DEFAULT '[]',
                        is_active BOOLEAN DEFAULT 1,
                        created_time TEXT NOT NULL,
                        created_by TEXT DEFAULT 'system',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (device_group_id) REFERENCES device_groups (group_id),
                        FOREIGN KEY (role_id) REFERENCES roles (role_id)
                    )
                """)
                
                # Индексы
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_policies_group ON access_policies(device_group_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_policies_role ON access_policies(role_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_policies_active ON access_policies(is_active)")
                
                conn.commit()
                logger.info("База данных RBAC инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации БД RBAC: {e}")
            raise
    
    def create_default_roles(self):
        """Создание системных ролей по умолчанию"""
        default_roles = [
            {
                'name': 'Farm Administrator',
                'description': 'Полный доступ к управлению фермой',
                'permissions': [
                    Permission.DEVICE_VIEW.value,
                    Permission.DEVICE_CONNECT.value,
                    Permission.DEVICE_CONFIGURE.value,
                    Permission.DEVICE_MANAGE.value,
                    Permission.VPN_ACCESS.value,
                    Permission.VNC_ACCESS.value,
                    Permission.HTTP_ACCESS.value,
                    Permission.SSH_ACCESS.value,
                    Permission.API_ACCESS.value,
                    Permission.DEVICE_REGISTER.value
                ]
            },
            {
                'name': 'Farm Operator',
                'description': 'Доступ к мониторингу и базовому управлению',
                'permissions': [
                    Permission.DEVICE_VIEW.value,
                    Permission.DEVICE_CONNECT.value,
                    Permission.VNC_ACCESS.value,
                    Permission.HTTP_ACCESS.value,
                    Permission.API_ACCESS.value
                ]
            },
            {
                'name': 'Service Engineer',
                'description': 'Доступ для обслуживания и диагностики',
                'permissions': [
                    Permission.DEVICE_VIEW.value,
                    Permission.DEVICE_CONNECT.value,
                    Permission.DEVICE_CONFIGURE.value,
                    Permission.VPN_ACCESS.value,
                    Permission.VNC_ACCESS.value,
                    Permission.SSH_ACCESS.value,
                    Permission.API_ACCESS.value
                ]
            },
            {
                'name': 'Read Only',
                'description': 'Доступ только для просмотра',
                'permissions': [
                    Permission.DEVICE_VIEW.value,
                    Permission.API_ACCESS.value
                ]
            },
            {
                'name': 'System Administrator',
                'description': 'Полный административный доступ',
                'permissions': [perm.value for perm in Permission]
            }
        ]
        
        for role_data in default_roles:
            existing_role = self.get_role_by_name(role_data['name'])
            if not existing_role:
                self.create_role(
                    name=role_data['name'],
                    description=role_data['description'],
                    permissions=role_data['permissions'],
                    is_system_role=True
                )
    
    def create_role(self, 
                   name: str,
                   description: str,
                   permissions: List[str],
                   is_system_role: bool = False,
                   created_by: str = "system") -> str:
        """Создание новой роли"""
        role_id = secrets.token_urlsafe(16)
        
        role = Role(
            role_id=role_id,
            name=name,
            description=description,
            permissions=permissions,
            is_system_role=is_system_role,
            created_time=datetime.now().isoformat(),
            created_by=created_by
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO roles 
                    (role_id, name, description, permissions, is_system_role, created_time, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    role.role_id,
                    role.name,
                    role.description,
                    json.dumps(role.permissions),
                    role.is_system_role,
                    role.created_time,
                    role.created_by
                ))
                conn.commit()
                
                logger.info(f"Создана роль {name} ({role_id})")
                return role_id
                
        except Exception as e:
            logger.error(f"Ошибка создания роли: {e}")
            raise
    
    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Получение роли по имени"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT * FROM roles WHERE name = ?
                """, (name,))
                
                row = cursor.fetchone()
                if row:
                    return Role(
                        role_id=row[0],
                        name=row[1],
                        description=row[2] or "",
                        permissions=json.loads(row[3]),
                        is_system_role=bool(row[4]),
                        created_time=row[5],
                        created_by=row[6]
                    )
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения роли {name}: {e}")
            return None
    
    def create_user(self,
                   username: str,
                   email: str,
                   full_name: str,
                   password: str,
                   roles: List[str] = None,
                   is_admin: bool = False) -> str:
        """Создание нового пользователя"""
        if roles is None:
            roles = []
        
        user_id = secrets.token_urlsafe(16)
        password_hash = hashlib.sha256((password + user_id).encode()).hexdigest()
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            is_admin=is_admin,
            roles=roles,
            created_time=datetime.now().isoformat()
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO users 
                    (user_id, username, email, full_name, password_hash, is_admin, roles, created_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.user_id,
                    user.username,
                    user.email,
                    user.full_name,
                    user.password_hash,
                    user.is_admin,
                    json.dumps(user.roles),
                    user.created_time
                ))
                conn.commit()
                
                logger.info(f"Создан пользователь {username} ({user_id})")
                return user_id
                
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            raise
    
    def create_device_group(self,
                           name: str,
                           description: str,
                           device_ids: List[str] = None,
                           device_types: List[str] = None,
                           tags_filter: List[str] = None,
                           parent_group_id: str = "",
                           created_by: str = "system") -> str:
        """Создание группы устройств"""
        if device_ids is None:
            device_ids = []
        if device_types is None:
            device_types = []
        if tags_filter is None:
            tags_filter = []
        
        group_id = secrets.token_urlsafe(16)
        
        group = DeviceGroup(
            group_id=group_id,
            name=name,
            description=description,
            device_ids=device_ids,
            device_types=device_types,
            tags_filter=tags_filter,
            parent_group_id=parent_group_id,
            created_time=datetime.now().isoformat(),
            created_by=created_by
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO device_groups
                    (group_id, name, description, device_ids, device_types, tags_filter, 
                     parent_group_id, created_time, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    group.group_id,
                    group.name,
                    group.description,
                    json.dumps(group.device_ids),
                    json.dumps(group.device_types),
                    json.dumps(group.tags_filter),
                    group.parent_group_id,
                    group.created_time,
                    group.created_by
                ))
                conn.commit()
                
                logger.info(f"Создана группа устройств {name} ({group_id})")
                return group_id
                
        except Exception as e:
            logger.error(f"Ошибка создания группы устройств: {e}")
            raise
    
    def create_access_policy(self,
                           name: str,
                           description: str,
                           device_group_id: str,
                           role_id: str,
                           permissions: List[str],
                           time_restrictions: Dict[str, Any] = None,
                           ip_restrictions: List[str] = None,
                           created_by: str = "system") -> str:
        """Создание политики доступа"""
        policy_id = secrets.token_urlsafe(16)
        
        policy = AccessPolicy(
            policy_id=policy_id,
            name=name,
            description=description,
            device_group_id=device_group_id,
            role_id=role_id,
            permissions=permissions,
            time_restrictions=time_restrictions or {},
            ip_restrictions=ip_restrictions or [],
            created_time=datetime.now().isoformat(),
            created_by=created_by
        )
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO access_policies
                    (policy_id, name, description, device_group_id, role_id, permissions,
                     time_restrictions, ip_restrictions, created_time, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    policy.policy_id,
                    policy.name,
                    policy.description,
                    policy.device_group_id,
                    policy.role_id,
                    json.dumps(policy.permissions),
                    json.dumps(policy.time_restrictions),
                    json.dumps(policy.ip_restrictions),
                    policy.created_time,
                    policy.created_by
                ))
                conn.commit()
                
                logger.info(f"Создана политика доступа {name} ({policy_id})")
                return policy_id
                
        except Exception as e:
            logger.error(f"Ошибка создания политики доступа: {e}")
            raise
    
    def get_user_permissions(self, user_id: str, device_id: str = None) -> Set[str]:
        """Получение всех разрешений пользователя для устройства"""
        permissions = set()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Получаем пользователя
                cursor = conn.execute("""
                    SELECT roles, is_admin FROM users WHERE user_id = ? AND is_active = 1
                """, (user_id,))
                
                user_row = cursor.fetchone()
                if not user_row:
                    return permissions
                
                user_roles = json.loads(user_row[0])
                is_admin = bool(user_row[1])
                
                # Администратор имеет все права
                if is_admin:
                    return {perm.value for perm in Permission}
                
                # Получаем разрешения из ролей
                if user_roles:
                    placeholders = ','.join('?' * len(user_roles))
                    cursor = conn.execute(f"""
                        SELECT permissions FROM roles 
                        WHERE role_id IN ({placeholders})
                    """, user_roles)
                    
                    for row in cursor.fetchall():
                        role_permissions = json.loads(row[0])
                        permissions.update(role_permissions)
                
                # Если указано конкретное устройство, проверяем политики доступа
                if device_id:
                    # Находим группы, содержащие это устройство
                    cursor = conn.execute("""
                        SELECT group_id, device_ids, device_types, tags_filter 
                        FROM device_groups
                    """)
                    
                    device_groups = []
                    for row in cursor.fetchall():
                        group_id = row[0]
                        device_ids = json.loads(row[1])
                        device_types = json.loads(row[2])
                        tags_filter = json.loads(row[3])
                        
                        # Проверяем принадлежность устройства к группе
                        # (упрощенная проверка, в реальности нужна интеграция с device_registry)
                        if device_id in device_ids:
                            device_groups.append(group_id)
                    
                    # Получаем дополнительные разрешения из политик
                    if device_groups:
                        placeholders = ','.join('?' * len(device_groups))
                        role_placeholders = ','.join('?' * len(user_roles)) if user_roles else "''"
                        
                        query = f"""
                            SELECT permissions FROM access_policies
                            WHERE device_group_id IN ({placeholders})
                            AND role_id IN ({role_placeholders})
                            AND is_active = 1
                        """
                        
                        cursor = conn.execute(query, device_groups + user_roles)
                        
                        for row in cursor.fetchall():
                            policy_permissions = json.loads(row[0])
                            permissions.update(policy_permissions)
                
                return permissions
                
        except Exception as e:
            logger.error(f"Ошибка получения разрешений пользователя {user_id}: {e}")
            return set()
    
    def check_user_permission(self, user_id: str, permission: str, device_id: str = None) -> bool:
        """Проверка разрешения пользователя"""
        user_permissions = self.get_user_permissions(user_id, device_id)
        return permission in user_permissions
    
    def get_user_accessible_devices(self, user_id: str, all_devices: List[Dict]) -> List[Dict]:
        """Получение списка устройств, доступных пользователю"""
        try:
            accessible_devices = []
            
            # Проверяем каждое устройство
            for device in all_devices:
                device_id = device.get('device_id') or device.get('id')
                if self.check_user_permission(user_id, Permission.DEVICE_VIEW.value, device_id):
                    accessible_devices.append(device)
            
            return accessible_devices
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных устройств для {user_id}: {e}")
            return []
    
    def get_rbac_stats(self) -> Dict[str, Any]:
        """Получение статистики RBAC системы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Статистика пользователей
                cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
                active_users = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1 AND is_active = 1")
                admin_users = cursor.fetchone()[0]
                
                # Статистика ролей
                cursor = conn.execute("SELECT COUNT(*) FROM roles")
                total_roles = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM roles WHERE is_system_role = 1")
                system_roles = cursor.fetchone()[0]
                
                # Статистика групп и политик
                cursor = conn.execute("SELECT COUNT(*) FROM device_groups")
                device_groups = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM access_policies WHERE is_active = 1")
                active_policies = cursor.fetchone()[0]
                
                return {
                    "active_users": active_users,
                    "admin_users": admin_users,
                    "total_roles": total_roles,
                    "system_roles": system_roles,
                    "device_groups": device_groups,
                    "active_policies": active_policies,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики RBAC: {e}")
            return {}

# Глобальный экземпляр RBAC системы
_rbac_system: Optional[RBACSystem] = None

def get_rbac_system() -> RBACSystem:
    """Получение глобального экземпляра RBAC системы"""
    global _rbac_system
    if not _rbac_system:
        db_path = os.path.join(os.path.dirname(__file__), "rbac_system.db")
        _rbac_system = RBACSystem(db_path)
    return _rbac_system

# Декоратор для проверки разрешений
def require_permission(permission: str, device_id_param: str = None):
    """Декоратор для проверки разрешений в Flask routes"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            from flask import request, jsonify, session
            
            # Получаем user_id из сессии (упрощенная аутентификация)
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({
                    'status': 'error',
                    'message': 'Не авторизован'
                }), 401
            
            # Получаем device_id если указан параметр
            device_id = None
            if device_id_param:
                device_id = kwargs.get(device_id_param) or request.json.get(device_id_param) if request.json else None
            
            # Проверяем разрешение
            rbac = get_rbac_system()
            if not rbac.check_user_permission(user_id, permission, device_id):
                return jsonify({
                    'status': 'error',
                    'message': 'Недостаточно прав доступа'
                }), 403
            
            return func(*args, **kwargs)
        
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

if __name__ == "__main__":
    # Тест RBAC системы
    rbac = RBACSystem("test_rbac.db")
    
    print("=== Тест RBAC системы ===")
    
    # Создаем тестового пользователя
    admin_role = rbac.get_role_by_name("System Administrator")
    operator_role = rbac.get_role_by_name("Farm Operator")
    
    if admin_role and operator_role:
        user_id = rbac.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password="password123",
            roles=[operator_role.role_id]
        )
        
        print(f"Создан пользователь: {user_id}")
        
        # Создаем группу устройств
        group_id = rbac.create_device_group(
            name="Main Farm Devices",
            description="Основные устройства фермы",
            device_types=["farm"],
            tags_filter=["production"]
        )
        
        print(f"Создана группа устройств: {group_id}")
        
        # Создаем политику доступа
        policy_id = rbac.create_access_policy(
            name="Farm Operator Access",
            description="Доступ оператора к устройствам фермы",
            device_group_id=group_id,
            role_id=operator_role.role_id,
            permissions=[
                Permission.DEVICE_VIEW.value,
                Permission.VNC_ACCESS.value
            ]
        )
        
        print(f"Создана политика доступа: {policy_id}")
        
        # Проверяем разрешения
        permissions = rbac.get_user_permissions(user_id)
        print(f"Разрешения пользователя: {list(permissions)}")
        
        # Проверяем конкретное разрешение
        can_view = rbac.check_user_permission(user_id, Permission.DEVICE_VIEW.value)
        can_delete = rbac.check_user_permission(user_id, Permission.DEVICE_DELETE.value)
        
        print(f"Может просматривать устройства: {can_view}")
        print(f"Может удалять устройства: {can_delete}")
        
        # Статистика
        stats = rbac.get_rbac_stats()
        print(f"Статистика RBAC: {stats}")
    
    print("✅ Тест RBAC завершен")