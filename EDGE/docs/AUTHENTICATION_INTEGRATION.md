# 🔐 EDGE Authentication Integration

Интеграция EDGE устройств с SERVER системой аутентификации через API ключи.

## 🏗️ Архитектура интеграции

```
📱 EDGE Device              🌐 SERVER                    🖥️ APP/Dashboard
     │                         │                           │
     ├─ API Key Auth           ├─ JWT Validation           ├─ JWT Token
     ├─ Device Registration    ├─ API Key Validation       ├─ User Session
     ├─ Heartbeat Service      ├─ Device Management        ├─ Web Interface
     ├─ Data Transmission      ├─ Role-based Access        └─ Mobile App
     └─ P2P Tunnel Request     └─ Secure Storage
```

## 🔑 Система ключей

### Получение API ключа для EDGE

1. **Администратор регистрирует устройство:**
```bash
cd SERVER
python3 admin_cli.py register-device \
    --owner-id user_farmer1234 \
    --farm-id farm_greenhouse_01 \
    --device-name "EDGE-Теплица-Вент" \
    --device-type EDGE

# Результат:
# ✅ EDGE device registered successfully
# 🔑 API KEY: edge_Ail8G8yVJ7TroLe5BUnCFFqX2epemNSDG8XsGnWh-VM
# 📋 Environment variables for EDGE device:
#    export EDGE_API_KEY="edge_Ail8G8yVJ7TroLe5BUnCFFqX2epemNSDG8XsGnWh-VM"
#    export EDGE_DEVICE_ID="edge_bb27af47791f"
#    export EDGE_FARM_ID="farm_greenhouse_01"
```

2. **На EDGE устройстве настраиваем переменные окружения:**
```bash
# /opt/edge-device/.env
export EDGE_API_KEY="edge_Ail8G8yVJ7TroLe5BUnCFFqX2epemNSDG8XsGnWh-VM"
export EDGE_DEVICE_ID="edge_bb27af47791f"
export EDGE_FARM_ID="farm_greenhouse_01"
export TUNNEL_BROKER_URL="https://your-server.com:8080"
export HEARTBEAT_INTERVAL="60"
```

## 💻 Интеграция с EDGE кодом

### 1. Authenticated HTTP Client

```python
from core.edge_authentication import EDGEAuthenticatedClient, load_auth_config_from_env

# Инициализация клиента
config = load_auth_config_from_env()
client = EDGEAuthenticatedClient(config)

# Проверка аутентификации
if client.authenticate():
    print("✅ Connected to SERVER")
else:
    print("❌ Authentication failed")
```

### 2. Отправка данных КУБ устройств

```python
# Получаем данные от всех КУБ устройств
from core.unified_system import UnifiedSystem
from core.device_registry import DeviceRegistry

unified = UnifiedSystem()
registry = DeviceRegistry()

# Собираем данные всех устройств
device_data = {}
for device_info in registry.get_all_devices():
    manager = unified.get_device_manager(device_info.device_id)
    if manager:
        variables = manager.get_all_variables()
        device_data[str(device_info.device_id)] = {
            'type': device_info.device_type.value,
            'name': device_info.name,
            'variables': {var.name: var.current_value for var in variables},
            'last_update': manager.last_update.isoformat() if manager.last_update else None
        }

# Отправляем на SERVER
success = client.send_data({
    'kub_devices': device_data,
    'system_info': {
        'uptime': time.time() - start_time,
        'memory_usage': psutil.virtual_memory().percent,
        'last_modbus_poll': last_poll_time.isoformat()
    }
})
```

### 3. Heartbeat Service

```python
from core.edge_authentication import EDGEHeartbeatService
import threading

# Функция для получения текущего состояния
def get_system_status():
    return {
        'devices_count': len(registry.get_all_devices()),
        'active_devices': sum(1 for d in registry.get_all_devices() if d.is_active),
        'last_poll': unified.last_successful_poll.isoformat() if unified.last_successful_poll else None,
        'errors': len(unified.get_recent_errors())
    }

# Запуск heartbeat сервиса в отдельном потоке
heartbeat_service = EDGEHeartbeatService(client)
heartbeat_thread = threading.Thread(
    target=heartbeat_service.start,
    args=(get_system_status,),
    daemon=True
)
heartbeat_thread.start()
```

### 4. P2P Tunnel Integration

```python
# Запрос туннеля для подключения к другому EDGE устройству
tunnel_info = client.request_tunnel_connection("edge_target_device_id")

if tunnel_info:
    # Используем tunnel_integration.py для установки соединения
    from core.tunnel_integration import EDGETunnelClient
    
    tunnel_client = EDGETunnelClient(
        broker_url=tunnel_info['broker_url'],
        auth_token=tunnel_info['tunnel_token']
    )
    
    # Подключаемся через P2P туннель
    if tunnel_client.connect_to_peer(tunnel_info['peer_id']):
        remote_data = tunnel_client.get_current_data()
        print(f"📊 Received data from remote EDGE: {remote_data}")
```

## 🚀 Запуск EDGE с аутентификацией

### Обновленный start_edge.py

```python
#!/usr/bin/env python3
"""
Запуск EDGE системы с интеграцией SERVER аутентификации
"""

import os
import time
import logging
import threading
from datetime import datetime

from core.unified_system import UnifiedSystem
from core.device_registry import DeviceRegistry
from core.edge_authentication import (
    load_auth_config_from_env, 
    EDGEAuthenticatedClient,
    EDGEHeartbeatService
)

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting EDGE system with SERVER authentication")
    
    # 1. Инициализируем аутентификацию
    try:
        auth_config = load_auth_config_from_env()
        auth_client = EDGEAuthenticatedClient(auth_config)
        
        # Проверяем подключение к SERVER
        if not auth_client.authenticate():
            logger.error("❌ Failed to authenticate with SERVER")
            return
        
        logger.info(f"✅ Authenticated as {auth_config.device_id}")
        
    except Exception as e:
        logger.error(f"❌ Authentication setup failed: {e}")
        return
    
    # 2. Инициализируем EDGE системы
    registry = DeviceRegistry()
    registry.load_from_config()
    
    unified = UnifiedSystem()
    unified.initialize_all_devices()
    
    logger.info(f"📱 Loaded {len(registry.get_all_devices())} КУБ devices")
    
    # 3. Функция для сбора данных
    def collect_system_data():
        device_data = {}
        for device_info in registry.get_all_devices():
            try:
                manager = unified.get_device_manager(device_info.device_id)
                if manager:
                    variables = manager.get_all_variables()
                    device_data[str(device_info.device_id)] = {
                        'type': device_info.device_type.value,
                        'name': device_info.name,
                        'variables': {var.name: var.current_value for var in variables},
                        'last_update': manager.last_update.isoformat() if manager.last_update else None
                    }
            except Exception as e:
                logger.warning(f"Error collecting data from device {device_info.device_id}: {e}")
        
        return {
            'devices_count': len(device_data),
            'active_devices': len([d for d in device_data.values() if d['last_update']]),
            'timestamp': datetime.now().isoformat()
        }
    
    # 4. Запускаем heartbeat сервис
    heartbeat_service = EDGEHeartbeatService(auth_client)
    heartbeat_thread = threading.Thread(
        target=heartbeat_service.start,
        args=(collect_system_data,),
        daemon=True
    )
    heartbeat_thread.start()
    
    # 5. Основной цикл работы
    logger.info("🔄 Starting main monitoring loop")
    data_send_interval = 300  # 5 минут
    last_data_send = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Обновляем данные всех устройств
            unified.update_all_devices()
            
            # Отправляем данные на SERVER каждые 5 минут
            if current_time - last_data_send >= data_send_interval:
                system_data = collect_system_data()
                
                full_data = {
                    'kub_devices': {},
                    'system_info': system_data
                }
                
                # Собираем детальные данные устройств
                for device_info in registry.get_all_devices():
                    manager = unified.get_device_manager(device_info.device_id)
                    if manager:
                        variables = manager.get_all_variables()
                        full_data['kub_devices'][str(device_info.device_id)] = {
                            'type': device_info.device_type.value,
                            'variables': {var.name: var.current_value for var in variables}
                        }
                
                # Отправляем на SERVER
                if auth_client.send_data(full_data):
                    logger.info("📊 Data sent to SERVER successfully")
                else:
                    logger.warning("⚠️ Failed to send data to SERVER")
                
                last_data_send = current_time
            
            time.sleep(10)  # Основной цикл каждые 10 секунд
            
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down EDGE system")
        heartbeat_service.stop()

if __name__ == "__main__":
    main()
```

## 🔧 Настройки безопасности

### 1. Защита API ключей

```bash
# Создаем защищенный файл с переменными окружения
sudo mkdir -p /etc/edge-device
sudo chmod 700 /etc/edge-device

sudo tee /etc/edge-device/auth.env << EOF
EDGE_API_KEY="edge_Ail8G8yVJ7TroLe5BUnCFFqX2epemNSDG8XsGnWh-VM"
EDGE_DEVICE_ID="edge_bb27af47791f"
EDGE_FARM_ID="farm_greenhouse_01"
TUNNEL_BROKER_URL="https://your-server.com:8080"
EOF

sudo chmod 600 /etc/edge-device/auth.env
sudo chown edge-user:edge-user /etc/edge-device/auth.env
```

### 2. Systemd Service

```ini
# /etc/systemd/system/edge-device.service
[Unit]
Description=EDGE Device Service
After=network.target

[Service]
Type=simple
User=edge-user
WorkingDirectory=/opt/edge-device
EnvironmentFile=/etc/edge-device/auth.env
ExecStart=/usr/bin/python3 start_edge.py
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/edge-device/data

[Install]
WantedBy=multi-user.target
```

## 📊 Мониторинг аутентификации

### 1. Логи аутентификации

```python
import logging

# Настройка логирования аутентификации
auth_logger = logging.getLogger('edge.auth')
auth_handler = logging.handlers.RotatingFileHandler(
    '/opt/edge-device/logs/auth.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
auth_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
auth_logger.addHandler(auth_handler)

# В EDGEAuthenticatedClient добавляем логи:
def authenticate(self) -> bool:
    auth_logger.info(f"Authentication attempt for device {self.config.device_id}")
    # ... код аутентификации ...
    if success:
        auth_logger.info("Authentication successful")
    else:
        auth_logger.error("Authentication failed")
```

### 2. Метрики подключения

```python
# В heartbeat сообщения добавляем метрики
def collect_system_data():
    return {
        'devices_count': len(registry.get_all_devices()),
        'auth_status': 'authenticated',
        'last_auth_check': last_auth_time.isoformat(),
        'connection_quality': calculate_connection_quality(),
        'api_requests_count': api_request_counter,
        'failed_requests_count': failed_request_counter
    }
```

## 🎯 Результат

**Полная интеграция EDGE устройств с SERVER системой аутентификации:**

✅ **API ключи** для безопасной аутентификации  
✅ **Heartbeat сервис** для мониторинга состояния  
✅ **Автоматическая отправка данных** КУБ устройств  
✅ **P2P туннели** через SERVER брокер  
✅ **Централизованное управление** устройствами  
✅ **Безопасность** на уровне предприятия  

EDGE устройства теперь полностью интегрированы с SERVER и могут работать в составе распределенной системы мониторинга!