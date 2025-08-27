-- ===============================================================================
-- MULTI-TENANT DATABASE SCHEMA ДЛЯ CUBE_RS
-- Система привязки пользователей к конкретному оборудованию (как у IXON)
-- ===============================================================================

-- 1. ОРГАНИЗАЦИИ/КЛИЕНТЫ (Фермеры, компании)
CREATE TABLE organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- "Ферма Иванова", "ООО Агрохолдинг"
    code TEXT UNIQUE NOT NULL,             -- "IVANOV_FARM", "AGRO_LLC" 
    description TEXT,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

-- 2. КУБ-УСТРОЙСТВА с привязкой к организациям
CREATE TABLE kub_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,      -- Привязка к организации
    device_id TEXT UNIQUE NOT NULL,        -- Уникальный ID устройства "KUB_001", "FARM_A_01"
    device_name TEXT NOT NULL,             -- Понятное имя "Птичник №1", "Основной инкубатор"
    modbus_slave_id INTEGER NOT NULL,      -- Modbus Slave ID (1-247)
    device_type TEXT DEFAULT 'KUB-1063',
    location TEXT,                         -- "Птичник А", "Цех 2", "Корпус 1"
    installation_date DATE,
    serial_number TEXT,
    firmware_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    
    FOREIGN KEY (organization_id) REFERENCES organizations (id)
);

-- 3. ПОЛЬЗОВАТЕЛИ с ролями в организациях
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,            -- ID Telegram пользователя
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

-- 4. РОЛИ ПОЛЬЗОВАТЕЛЕЙ В ОРГАНИЗАЦИЯХ (многие ко многим)
CREATE TABLE user_organization_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL,
    role TEXT NOT NULL,                    -- 'owner', 'admin', 'operator', 'viewer'
    granted_by INTEGER,                    -- Кто предоставил доступ
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,                  -- Срок действия доступа
    is_active INTEGER DEFAULT 1,
    
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (organization_id) REFERENCES organizations (id),
    FOREIGN KEY (granted_by) REFERENCES users (id),
    
    UNIQUE(user_id, organization_id, role)
);

-- 5. ДОСТУП К КОНКРЕТНЫМ УСТРОЙСТВАМ (гранулярные права)
CREATE TABLE user_device_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    access_level TEXT NOT NULL,            -- 'read', 'write', 'admin'
    granted_by INTEGER,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (device_id) REFERENCES kub_devices (id),
    FOREIGN KEY (granted_by) REFERENCES users (id),
    
    UNIQUE(user_id, device_id, access_level)
);

-- 6. АУДИТ ДОСТУПА К УСТРОЙСТВАМ
CREATE TABLE device_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    action TEXT NOT NULL,                  -- 'read_data', 'write_register', 'reset_alarms'
    details TEXT,                          -- JSON с деталями операции
    ip_address TEXT,
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success INTEGER NOT NULL,
    error_message TEXT,
    
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (device_id) REFERENCES kub_devices (id)
);

-- 7. УВЕДОМЛЕНИЯ И АЛЕРТЫ по устройствам
CREATE TABLE device_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,              -- 'alarm', 'warning', 'maintenance'
    severity TEXT NOT NULL,                -- 'critical', 'high', 'medium', 'low'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSON,                            -- Дополнительные данные в JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by INTEGER,
    resolved_at TIMESTAMP,
    resolved_by INTEGER,
    is_active INTEGER DEFAULT 1,
    
    FOREIGN KEY (device_id) REFERENCES kub_devices (id),
    FOREIGN KEY (acknowledged_by) REFERENCES users (id),
    FOREIGN KEY (resolved_by) REFERENCES users (id)
);

-- 8. ПОДПИСКИ НА УВЕДОМЛЕНИЯ
CREATE TABLE user_alert_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    device_id INTEGER,                     -- NULL = все устройства организации
    organization_id INTEGER,               -- Подписка на всю организацию
    alert_types TEXT NOT NULL,             -- JSON массив типов алертов
    notification_channels TEXT NOT NULL,   -- JSON: telegram, email, sms
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (device_id) REFERENCES kub_devices (id),
    FOREIGN KEY (organization_id) REFERENCES organizations (id)
);

-- ===============================================================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- ===============================================================================

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_kub_devices_org_id ON kub_devices(organization_id);
CREATE INDEX idx_kub_devices_slave_id ON kub_devices(modbus_slave_id);
CREATE INDEX idx_user_org_roles_user ON user_organization_roles(user_id);
CREATE INDEX idx_user_org_roles_org ON user_organization_roles(organization_id);
CREATE INDEX idx_user_device_access_user ON user_device_access(user_id);
CREATE INDEX idx_user_device_access_device ON user_device_access(device_id);
CREATE INDEX idx_device_access_log_user ON device_access_log(user_id);
CREATE INDEX idx_device_access_log_device ON device_access_log(device_id);
CREATE INDEX idx_device_access_log_timestamp ON device_access_log(timestamp);

-- ===============================================================================
-- ПРЕДСТАВЛЕНИЯ ДЛЯ УДОБНОГО ДОСТУПА
-- ===============================================================================

-- Представление: Пользователи с их организациями и ролями
CREATE VIEW user_organization_access AS
SELECT 
    u.id as user_id,
    u.telegram_id,
    u.username,
    u.first_name,
    u.last_name,
    o.id as organization_id,
    o.name as organization_name,
    o.code as organization_code,
    uor.role,
    uor.granted_at,
    uor.expires_at,
    uor.is_active
FROM users u
JOIN user_organization_roles uor ON u.id = uor.user_id
JOIN organizations o ON uor.organization_id = o.id
WHERE u.is_active = 1 AND uor.is_active = 1 AND o.is_active = 1;

-- Представление: Доступные устройства для пользователя
CREATE VIEW user_device_permissions AS
SELECT DISTINCT
    u.id as user_id,
    u.telegram_id,
    kd.id as device_id,
    kd.device_id as device_code,
    kd.device_name,
    kd.modbus_slave_id,
    kd.location,
    o.id as organization_id,
    o.name as organization_name,
    COALESCE(uda.access_level, 'read') as access_level
FROM users u
JOIN user_organization_roles uor ON u.id = uor.user_id
JOIN organizations o ON uor.organization_id = o.id
JOIN kub_devices kd ON o.id = kd.organization_id
LEFT JOIN user_device_access uda ON u.id = uda.user_id AND kd.id = uda.device_id AND uda.is_active = 1
WHERE u.is_active = 1 
  AND uor.is_active = 1 
  AND o.is_active = 1 
  AND kd.is_active = 1
  AND (uor.expires_at IS NULL OR uor.expires_at > datetime('now'))
  AND (uda.expires_at IS NULL OR uda.expires_at > datetime('now'));

-- ===============================================================================
-- НАЧАЛЬНЫЕ ДАННЫЕ ДЛЯ ДЕМОНСТРАЦИИ
-- ===============================================================================

-- Добавляем тестовые организации
INSERT INTO organizations (name, code, description, contact_person, phone, email) VALUES
('Ферма Иванова', 'IVANOV_FARM', 'Птицеводческое хозяйство', 'Иванов И.И.', '+7-900-123-45-67', 'ivanov@farm.ru'),
('Агрохолдинг Сибирь', 'AGRO_SIBERIA', 'Крупное агропредприятие', 'Петров П.П.', '+7-900-234-56-78', 'info@agrosib.ru'),
('Тепличный комплекс Юг', 'GREENHOUSE_SOUTH', 'Тепличное хозяйство', 'Сидорова С.С.', '+7-900-345-67-89', 'admin@greenhouse-south.ru');

-- Добавляем тестовые устройства
INSERT INTO kub_devices (organization_id, device_id, device_name, modbus_slave_id, location, serial_number) VALUES
(1, 'IVANOV_KUB_01', 'Птичник №1', 1, 'Основной корпус', 'KUB1063-2024-001'),
(1, 'IVANOV_KUB_02', 'Птичник №2', 2, 'Дополнительный корпус', 'KUB1063-2024-002'),
(2, 'AGRO_KUB_A1', 'Инкубатор А1', 3, 'Цех А', 'KUB1063-2024-003'),
(2, 'AGRO_KUB_A2', 'Инкубатор А2', 4, 'Цех А', 'KUB1063-2024-004'),
(2, 'AGRO_KUB_B1', 'Брудер Б1', 5, 'Цех Б', 'KUB1063-2024-005'),
(3, 'GREEN_KUB_01', 'Теплица №1', 6, 'Блок 1', 'KUB1063-2024-006');

-- Добавляем тестовых пользователей
INSERT INTO users (telegram_id, username, first_name, last_name, email, phone) VALUES
(123456789, 'farmer_ivan', 'Иван', 'Иванов', 'ivan@farm.ru', '+7-900-123-45-67'),
(987654321, 'agro_admin', 'Петр', 'Петров', 'admin@agrosib.ru', '+7-900-234-56-78'),
(555666777, 'greenhouse_operator', 'Анна', 'Сидорова', 'operator@greenhouse-south.ru', '+7-900-345-67-89');

-- Назначаем роли пользователям в организациях
INSERT INTO user_organization_roles (user_id, organization_id, role, granted_by) VALUES
(1, 1, 'owner', 1),    -- Иванов - владелец своей фермы
(2, 2, 'admin', 2),    -- Петров - админ агрохолдинга
(3, 3, 'operator', 3); -- Сидорова - оператор теплиц

-- Добавляем специфичные доступы к устройствам (опционально)
INSERT INTO user_device_access (user_id, device_id, access_level, granted_by) VALUES
(1, 1, 'admin', 1),    -- Иванов - полный доступ к своему КУБ №1
(1, 2, 'admin', 1),    -- Иванов - полный доступ к своему КУБ №2
(2, 3, 'admin', 2),    -- Петров - полный доступ ко всем устройствам агрохолдинга
(2, 4, 'admin', 2),
(2, 5, 'admin', 2);

-- ===============================================================================
-- ПОЛЕЗНЫЕ ЗАПРОСЫ ДЛЯ РАБОТЫ СИСТЕМЫ
-- ===============================================================================

-- Получить все устройства, доступные пользователю Telegram
/*
SELECT device_code, device_name, location, organization_name, access_level
FROM user_device_permissions 
WHERE telegram_id = ? 
ORDER BY organization_name, device_name;
*/

-- Проверить доступ пользователя к конкретному устройству
/*
SELECT access_level 
FROM user_device_permissions 
WHERE telegram_id = ? AND device_code = ?;
*/

-- Получить список алертов для пользователя
/*
SELECT da.* 
FROM device_alerts da
JOIN user_device_permissions udp ON da.device_id = udp.device_id
WHERE udp.telegram_id = ? AND da.is_active = 1
ORDER BY da.created_at DESC;
*/