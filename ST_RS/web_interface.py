#!/usr/bin/env python3
"""
Web Interface for Stienen Gateway
Веб-интерфейс для гейтвея Stienen (замена WinForms)
Современная замена оригинального Windows Forms интерфейса
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import asyncio
import logging
from pathlib import Path

from stienen.gateway_backend import StienenGatewayBackend
from stienen.rs485_protocol import StienenProtocolCmd
from stienen.variable_mapping import VariableValue

# Pydantic модели для API

class DeviceStatus(BaseModel):
    """Модель статуса устройства"""
    address: int
    name: str
    device_id: str
    hardware: int
    version: int
    online: bool
    last_communication: Optional[datetime]
    alarm_active: bool
    identification_in_progress: bool

class VariableInfo(BaseModel):
    """Модель информации о переменной"""
    name: str
    index: int
    length: int
    type: str
    current_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None

class SetVariableRequest(BaseModel):
    """Модель запроса установки переменной"""
    variable_name: str
    value: Any

class GatewayStats(BaseModel):
    """Модель статистики гейтвея"""
    name: str
    active: bool
    devices_total: int
    devices_online: int
    packets_sent: int
    packets_received: int
    packets_failed: int
    last_activity: Optional[datetime]
    rs485_connected: bool

class WebSocketManager:
    """Менеджер WebSocket соединений для real-time обновлений"""
    
    def __init__(self):
        self.connections: List[WebSocket] = []
        self.logger = logging.getLogger(__name__)
    
    async def connect(self, websocket: WebSocket):
        """Подключение нового WebSocket"""
        await websocket.accept()
        self.connections.append(websocket)
        self.logger.info(f"WebSocket подключен. Всего: {len(self.connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Отключение WebSocket"""
        if websocket in self.connections:
            self.connections.remove(websocket)
            self.logger.info(f"WebSocket отключен. Осталось: {len(self.connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Рассылка сообщения всем подключенным клиентам"""
        if not self.connections:
            return
        
        message_str = json.dumps(message, default=str)
        disconnected = []
        
        for connection in self.connections:
            try:
                await connection.send_text(message_str)
            except:
                disconnected.append(connection)
        
        # Убираем отключенные соединения
        for conn in disconnected:
            self.disconnect(conn)

class StienenWebInterface:
    """Веб-интерфейс для гейтвея Stienen"""
    
    def __init__(self, gateway: StienenGatewayBackend, port: int = 8080):
        self.gateway = gateway
        self.port = port
        self.app = FastAPI(
            title="Stienen RS485 Gateway",
            description="Веб-интерфейс для управления контроллерами Stienen",
            version="1.0.0"
        )
        
        self.websocket_manager = WebSocketManager()
        self.logger = logging.getLogger(__name__)
        
        # Настройка CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Регистрируем маршруты
        self._setup_routes()
        
        # Задача для real-time обновлений
        self.update_task: Optional[asyncio.Task] = None
    
    def _setup_routes(self):
        """Настройка API маршрутов"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            """Главная страница"""
            return self._get_index_html()
        
        @self.app.get("/api/gateway/status", response_model=GatewayStats)
        async def get_gateway_status():
            """Получение статуса гейтвея"""
            stats = self.gateway.get_gateway_statistics()
            return GatewayStats(**stats)
        
        @self.app.get("/api/devices", response_model=List[DeviceStatus])
        async def get_devices():
            """Получение списка устройств"""
            devices_status = self.gateway.get_devices_status()
            return [DeviceStatus(**device) for device in devices_status]
        
        @self.app.get("/api/devices/{address}/variables", response_model=List[VariableInfo])
        async def get_device_variables(address: int):
            """Получение переменных устройства"""
            device = self.gateway.devices.get(address)
            if not device:
                raise HTTPException(status_code=404, detail="Устройство не найдено")
            
            # Получаем все переменные
            all_vars = self.gateway.variable_mapper.get_all_variables(
                device.hardware, device.version
            )
            
            # Получаем текущие значения
            current_values = self.gateway.get_all_device_values(address)
            
            variables = []
            for var_info in all_vars:
                var = VariableInfo(
                    name=var_info['name'],
                    index=var_info['index'],
                    length=var_info['length'],
                    type=var_info['type'],
                    current_value=current_values.get(var_info['name']),
                    min_value=var_info.get('min'),
                    max_value=var_info.get('max')
                )
                variables.append(var)
            
            return variables
        
        @self.app.put("/api/devices/{address}/variables/{variable_name}")
        async def set_device_variable(address: int, variable_name: str, request: SetVariableRequest):
            """Установка переменной устройства"""
            success = await self.gateway.set_device_variable(
                address, request.variable_name, request.value
            )
            
            if not success:
                raise HTTPException(status_code=400, detail="Не удалось установить переменную")
            
            return {"success": True, "message": f"Переменная {variable_name} установлена"}
        
        @self.app.post("/api/devices/{address}/identify")
        async def identify_device(address: int):
            """Запрос идентификации устройства"""
            if not self.gateway.rs485_comm:
                raise HTTPException(status_code=503, detail="RS485 коммуникация недоступна")
            
            msg_id = self.gateway.rs485_comm.send_message(
                dest=address,
                cmd=StienenProtocolCmd.IDENTIFICATION_REQ
            )
            
            return {"success": True, "message_id": msg_id}
        
        @self.app.post("/api/devices/add")
        async def add_device(address: int, name: str = "", hardware: int = 1001, version: int = 1):
            """Добавление нового устройства"""
            await self.gateway.add_device(address, name, hardware, version)
            return {"success": True, "message": f"Устройство {address} добавлено"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket для real-time обновлений"""
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    # Просто ждем, реальные данные отправляются через update_task
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.websocket_manager.disconnect(websocket)
    
    def _get_index_html(self) -> str:
        """Генерация HTML главной страницы"""
        return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stienen RS485 Gateway</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vue/3.3.4/vue.global.prod.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/axios/1.4.0/axios.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px;
        }
        
        .header {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .status-card {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .status-card:hover {
            transform: translateY(-5px);
        }
        
        .status-card h3 {
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-online { background: #27ae60; }
        .status-offline { background: #e74c3c; }
        .status-warning { background: #f39c12; }
        
        .devices-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .device-card {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .device-name {
            font-size: 1.3em;
            font-weight: bold;
            color: #2c3e50;
        }
        
        .variables-list {
            max-height: 300px;
            overflow-y: auto;
        }
        
        .variable-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        
        .variable-name {
            font-weight: 500;
            color: #34495e;
        }
        
        .variable-value {
            font-family: 'Courier New', monospace;
            color: #27ae60;
            font-weight: bold;
        }
        
        .btn {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: opacity 0.3s ease;
        }
        
        .btn:hover {
            opacity: 0.8;
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .input-group {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        
        .input-group input {
            flex: 1;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }
        
        .log-container {
            background: rgba(0,0,0,0.8);
            color: #00ff00;
            font-family: 'Courier New', monospace;
            border-radius: 10px;
            padding: 20px;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 20px;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: white;
            font-size: 1.2em;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
    </style>
</head>
<body>
    <div id="app">
        <div class="container">
            <!-- Заголовок -->
            <div class="header">
                <h1>🏭 Stienen RS485 Gateway</h1>
                <p>Современная система мониторинга контроллеров</p>
            </div>

            <!-- Загрузка -->
            <div v-if="loading" class="loading">
                <div class="pulse">⏳ Загрузка данных...</div>
            </div>

            <!-- Основной контент -->
            <div v-else>
                <!-- Статус гейтвея -->
                <div class="status-grid">
                    <div class="status-card">
                        <h3>🌐 Статус гейтвея</h3>
                        <div>
                            <span class="status-indicator" :class="gatewayStats.active ? 'status-online' : 'status-offline'"></span>
                            {{ gatewayStats.active ? 'Активен' : 'Неактивен' }}
                        </div>
                        <div style="margin-top: 10px;">
                            <strong>{{ gatewayStats.name }}</strong>
                        </div>
                    </div>
                    
                    <div class="status-card">
                        <h3>📡 RS485 соединение</h3>
                        <div>
                            <span class="status-indicator" :class="gatewayStats.rs485_connected ? 'status-online' : 'status-offline'"></span>
                            {{ gatewayStats.rs485_connected ? 'Подключено' : 'Отключено' }}
                        </div>
                    </div>
                    
                    <div class="status-card">
                        <h3>🏠 Устройства</h3>
                        <div>{{ gatewayStats.devices_online }} / {{ gatewayStats.devices_total }} онлайн</div>
                        <div style="margin-top: 5px; font-size: 0.9em; color: #666;">
                            {{ Math.round((gatewayStats.devices_online / gatewayStats.devices_total) * 100) || 0 }}% доступность
                        </div>
                    </div>
                    
                    <div class="status-card">
                        <h3>📊 Трафик</h3>
                        <div>📤 {{ gatewayStats.packets_sent }} отправлено</div>
                        <div>📥 {{ gatewayStats.packets_received }} получено</div>
                        <div>❌ {{ gatewayStats.packets_failed }} ошибок</div>
                    </div>
                </div>

                <!-- Устройства -->
                <div class="devices-grid">
                    <div v-for="device in devices" :key="device.address" class="device-card">
                        <div class="device-header">
                            <div>
                                <div class="device-name">
                                    <span class="status-indicator" :class="device.online ? 'status-online' : 'status-offline'"></span>
                                    {{ device.name }}
                                </div>
                                <div style="font-size: 0.9em; color: #666;">
                                    Адрес: {{ device.address }} | HW: {{ device.hardware }}.{{ device.version }}
                                </div>
                            </div>
                            <div>
                                <button class="btn" @click="identifyDevice(device.address)" :disabled="device.identification_in_progress">
                                    {{ device.identification_in_progress ? '⏳' : '🔍' }} ID
                                </button>
                            </div>
                        </div>
                        
                        <!-- Сигнализация -->
                        <div v-if="device.alarm_active" style="color: #e74c3c; margin-bottom: 10px;">
                            🚨 Активна тревога
                        </div>
                        
                        <!-- Переменные -->
                        <div class="variables-list">
                            <div v-for="variable in deviceVariables[device.address] || []" :key="variable.name" class="variable-item">
                                <span class="variable-name">{{ variable.name }}</span>
                                <span class="variable-value">{{ formatValue(variable.current_value) }}</span>
                            </div>
                        </div>
                        
                        <!-- Управление переменными -->
                        <div class="input-group">
                            <input v-model="newVariableValues[device.address]?.name" placeholder="Имя переменной">
                            <input v-model="newVariableValues[device.address]?.value" placeholder="Значение">
                            <button class="btn" @click="setVariable(device.address)">Установить</button>
                        </div>
                    </div>
                </div>

                <!-- Лог сообщений -->
                <div class="log-container">
                    <div><strong>📋 Лог событий (последние {{ logs.length }} записей):</strong></div>
                    <div v-for="log in logs.slice(-20)" :key="log.timestamp">
                        {{ formatTimestamp(log.timestamp) }} - {{ log.message }}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const { createApp } = Vue;

        createApp({
            data() {
                return {
                    loading: true,
                    gatewayStats: {},
                    devices: [],
                    deviceVariables: {},
                    newVariableValues: {},
                    logs: [],
                    websocket: null
                }
            },
            
            async mounted() {
                await this.loadInitialData();
                this.connectWebSocket();
                
                // Периодическое обновление
                setInterval(async () => {
                    await this.loadGatewayStats();
                    await this.loadDevices();
                }, 5000);
            },
            
            methods: {
                async loadInitialData() {
                    this.loading = true;
                    try {
                        await Promise.all([
                            this.loadGatewayStats(),
                            this.loadDevices()
                        ]);
                        
                        // Загружаем переменные для каждого устройства
                        for (const device of this.devices) {
                            await this.loadDeviceVariables(device.address);
                            this.$set(this.newVariableValues, device.address, { name: '', value: '' });
                        }
                    } finally {
                        this.loading = false;
                    }
                },
                
                async loadGatewayStats() {
                    try {
                        const response = await axios.get('/api/gateway/status');
                        this.gatewayStats = response.data;
                    } catch (error) {
                        console.error('Ошибка загрузки статуса гейтвея:', error);
                    }
                },
                
                async loadDevices() {
                    try {
                        const response = await axios.get('/api/devices');
                        this.devices = response.data;
                    } catch (error) {
                        console.error('Ошибка загрузки устройств:', error);
                    }
                },
                
                async loadDeviceVariables(address) {
                    try {
                        const response = await axios.get(`/api/devices/${address}/variables`);
                        this.$set(this.deviceVariables, address, response.data);
                    } catch (error) {
                        console.error(`Ошибка загрузки переменных устройства ${address}:`, error);
                    }
                },
                
                async identifyDevice(address) {
                    try {
                        await axios.post(`/api/devices/${address}/identify`);
                        this.addLog(`Запрос идентификации устройства ${address}`);
                    } catch (error) {
                        this.addLog(`Ошибка идентификации устройства ${address}: ${error.response?.data?.detail || error.message}`);
                    }
                },
                
                async setVariable(address) {
                    const varData = this.newVariableValues[address];
                    if (!varData.name || varData.value === '') {
                        alert('Введите имя переменной и значение');
                        return;
                    }
                    
                    try {
                        // Пытаемся конвертировать значение в правильный тип
                        let value = varData.value;
                        if (value === 'true' || value === 'false') {
                            value = value === 'true';
                        } else if (!isNaN(value)) {
                            value = parseFloat(value);
                        }
                        
                        await axios.put(`/api/devices/${address}/variables/${varData.name}`, {
                            variable_name: varData.name,
                            value: value
                        });
                        
                        this.addLog(`Установлена переменная ${varData.name} = ${value} для устройства ${address}`);
                        
                        // Очищаем поля
                        varData.name = '';
                        varData.value = '';
                        
                        // Обновляем переменные
                        await this.loadDeviceVariables(address);
                        
                    } catch (error) {
                        this.addLog(`Ошибка установки переменной: ${error.response?.data?.detail || error.message}`);
                    }
                },
                
                connectWebSocket() {
                    const wsUrl = `ws://${window.location.host}/ws`;
                    this.websocket = new WebSocket(wsUrl);
                    
                    this.websocket.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    };
                    
                    this.websocket.onclose = () => {
                        // Переподключение через 5 секунд
                        setTimeout(() => this.connectWebSocket(), 5000);
                    };
                },
                
                handleWebSocketMessage(data) {
                    if (data.type === 'device_update') {
                        // Обновляем данные устройства
                        this.loadDeviceVariables(data.address);
                    } else if (data.type === 'log') {
                        this.addLog(data.message);
                    }
                },
                
                addLog(message) {
                    this.logs.push({
                        timestamp: new Date(),
                        message: message
                    });
                    
                    // Ограничиваем количество логов
                    if (this.logs.length > 100) {
                        this.logs = this.logs.slice(-50);
                    }
                },
                
                formatValue(value) {
                    if (value === null || value === undefined) return '-';
                    if (typeof value === 'boolean') return value ? '✅ Да' : '❌ Нет';
                    if (typeof value === 'number') return value.toFixed(2);
                    return value;
                },
                
                formatTimestamp(timestamp) {
                    return new Date(timestamp).toLocaleTimeString();
                }
            }
        }).mount('#app');
    </script>
</body>
</html>
        """
    
    async def start_server(self):
        """Запуск веб-сервера"""
        import uvicorn
        
        # Запускаем задачу real-time обновлений
        self.update_task = asyncio.create_task(self._realtime_update_loop())
        
        self.logger.info(f"🌐 Запуск веб-интерфейса на http://localhost:{self.port}")
        
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()
    
    async def _realtime_update_loop(self):
        """Цикл real-time обновлений через WebSocket"""
        while True:
            try:
                # Отправляем статистику каждые 2 секунды
                stats = self.gateway.get_gateway_statistics()
                await self.websocket_manager.broadcast({
                    'type': 'stats_update',
                    'data': stats
                })
                
                # Проверяем изменения в устройствах
                devices_status = self.gateway.get_devices_status()
                await self.websocket_manager.broadcast({
                    'type': 'devices_update',
                    'data': devices_status
                })
                
                await asyncio.sleep(2.0)
                
            except Exception as e:
                self.logger.error(f"Ошибка в real-time обновлениях: {e}")
                await asyncio.sleep(5.0)

# CLI для запуска веб-интерфейса
async def run_web_interface():
    """Запуск веб-интерфейса"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Веб-интерфейс Stienen Gateway")
    parser.add_argument('--config', '-c', default='config.json', help='Файл конфигурации')
    parser.add_argument('--port', '-p', type=int, default=8080, help='Порт веб-сервера')
    parser.add_argument('--no-gateway', action='store_true', help='Запуск без гейтвея (только интерфейс)')
    
    args = parser.parse_args()
    
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    gateway = None
    
    if not args.no_gateway:
        # Загружаем конфигурацию и создаем гейтвей
        from stienen.main_application import ConfigurationManager
        
        config_manager = ConfigurationManager(args.config)
        config = config_manager.load_config()
        
        gateway_config = GatewayConfig(
            name=config['gateway']['name'],
            rs485_port=config['gateway']['rs485_port'],
            rs485_baudrate=config['gateway']['rs485_baudrate'],
            polling_interval=config['gateway']['polling_interval']
        )
        
        gateway = StienenGatewayBackend(gateway_config)
        
        # Инициализируем гейтвей
        if not await gateway.initialize():
            logger.error("Не удалось инициализировать гейтвей")
            return 1
        
        # Добавляем устройства
        for device_config in config.get('devices', []):
            if device_config.get('enabled', True):
                await gateway.add_device(
                    address=device_config['address'],
                    name=device_config.get('name', ''),
                    hardware=device_config.get('hardware', 1001),
                    version=device_config.get('version', 1)
                )
    else:
        # Создаем мок гейтвей для демонстрации
        gateway = create_mock_gateway()
    
    # Создаем и запускаем веб-интерфейс
    web_interface = StienenWebInterface(gateway, args.port)
    
    try:
        await web_interface.start_server()
    except KeyboardInterrupt:
        logger.info("Веб-интерфейс остановлен")
    finally:
        if gateway and hasattr(gateway, 'shutdown'):
            await gateway.shutdown()

def create_mock_gateway():
    """Создание мок гейтвея для демонстрации"""
    from unittest.mock import Mock
    
    mock_gateway = Mock()
    
    # Мок статистики
    mock_gateway.get_gateway_statistics.return_value = {
        'name': 'Demo Gateway',
        'active': True,
        'devices_total': 3,
        'devices_online': 2,
        'packets_sent': 1234,
        'packets_received': 1220,
        'packets_failed': 5,
        'last_activity': datetime.now(),
        'rs485_connected': True
    }
    
    # Мок устройств
    mock_gateway.get_devices_status.return_value = [
        {
            'address': 1,
            'name': 'Climate Controller',
            'device_id': 'device1',
            'hardware': 1001,
            'version': 1,
            'online': True,
            'last_communication': datetime.now(),
            'alarm_active': False,
            'identification_in_progress': False
        },
        {
            'address': 2,
            'name': 'Feed Controller',
            'device_id': 'device2', 
            'hardware': 1001,
            'version': 1,
            'online': True,
            'last_communication': datetime.now(),
            'alarm_active': True,
            'identification_in_progress': False
        },
        {
            'address': 3,
            'name': 'Water Controller',
            'device_id': 'device3',
            'hardware': 1001,
            'version': 1,
            'online': False,
            'last_communication': None,
            'alarm_active': False,
            'identification_in_progress': False
        }
    ]
    
    # Мок переменных (будет вызываться через variable_mapper)
    mock_gateway.variable_mapper = Mock()
    mock_gateway.variable_mapper.get_all_variables.return_value = [
        {'name': 'AirTemperature', 'index': 100, 'length': 2, 'type': 'SHORT', 'min': -50, 'max': 100},
        {'name': 'TargetTemperature', 'index': 102, 'length': 2, 'type': 'SHORT', 'min': -50, 'max': 100},
        {'name': 'FanEnabled', 'index': 200, 'length': 1, 'type': 'BOOL', 'min': 0, 'max': 1},
        {'name': 'Humidity', 'index': 104, 'length': 2, 'type': 'SHORT', 'min': 0, 'max': 100},
    ]
    
    # Мок значений переменных
    mock_values = {
        1: {'AirTemperature': 23.5, 'TargetTemperature': 22.0, 'FanEnabled': True, 'Humidity': 65.2},
        2: {'FeedLevel': 78.5, 'MotorRunning': False, 'DailyConsumption': 145.7},
        3: {'WaterLevel': None, 'PumpStatus': None}
    }
    
    mock_gateway.get_all_device_values = lambda addr: mock_values.get(addr, {})
    
    # Мок других методов
    mock_gateway.set_device_variable = Mock(return_value=True)
    mock_gateway.devices = {i: Mock(hardware=1001, version=1) for i in [1, 2, 3]}
    
    return mock_gateway

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        # Запуск веб-интерфейса
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # Убираем "web" из аргументов
        asyncio.run(run_web_interface())
    else:
        print("Использование:")
        print("  python web_interface.py web --config config.json")
        print("  python web_interface.py web --port 8080 --no-gateway")
