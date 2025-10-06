#!/usr/bin/env python3
"""
Real Data Web Interface for Stienen KL-6400
Веб-интерфейс с РЕАЛЬНЫМИ данными с контроллера KL-6400
"""

import asyncio
import json
import logging
import re
import os
import serial
import struct
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


class RealDataCollector:
    """
    Сборщик реальных данных с KL-6400
    """
    
    def __init__(self, port: str, baudrate: int = 38400):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.real_data = {
            "devices": {
                "1": {
                    "name": "KL-6400 Controller",
                    "address": 1,
                    "status": "unknown",
                    "last_seen": None,
                    "variables": {}
                },
                "2": {
                    "name": "Room Section", 
                    "address": 2,
                    "status": "unknown",
                    "last_seen": None,
                    "variables": {}
                },
                "3": {
                    "name": "Unknown Module",
                    "address": 3,
                    "status": "unknown", 
                    "last_seen": None,
                    "variables": {}
                }
            },
            "gateway": {
                "name": "KL-6400 Real Gateway",
                "status": "connecting",
                "uptime_start": datetime.now(),
                "port": port,
                "baudrate": baudrate,
                "packets_sent": 0,
                "packets_received": 0,
                "last_update": datetime.now()
            }
        }
        self.logger = logging.getLogger(__name__)
    
    def connect(self) -> bool:
        """Подключение к RS485"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=1.0
            )
            self.real_data["gateway"]["status"] = "connected"
            self.logger.info(f"✅ Подключено к {self.port}")
            return True
        except Exception as e:
            self.real_data["gateway"]["status"] = f"error: {str(e)}"
            self.logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    def create_get_data_request(self, device_addr: int, var_index: int, var_length: int = 2) -> bytes:
        """Создание GET_DATA_REQ"""
        start_byte = 0x0D
        bus_state = 0x00
        dest = device_addr
        source = 0xFE
        data_len = 4
        cmd = 0x08  # GET_DATA_REQ
        version = 0x01
        msg_id = (int(datetime.now().timestamp()) + device_addr) & 0xFFFF
        
        header = struct.pack('>BBBBHHBHH',
                           start_byte, bus_state, dest, source,
                           data_len, cmd, version, msg_id, 0)
        
        header_crc = 0
        for byte in header[:-2]:
            header_crc ^= byte
            
        header = header[:-2] + struct.pack('>H', header_crc)
        data = struct.pack('<HH', var_index, var_length)
        
        data_crc = 0
        for byte in data:
            data_crc ^= byte
        
        packet = header + data + struct.pack('<H', data_crc)
        return packet
    
    def parse_response(self, data: bytes) -> Optional[Dict]:
        """Парсинг ответа"""
        if len(data) < 12:
            return None
            
        try:
            start_byte, bus_state, dest, source = struct.unpack('BBBB', data[0:4])
            data_len, cmd, version, msg_id, header_crc = struct.unpack('>HBHHH', data[4:12])
            
            if start_byte != 0x0D or cmd != 0x09:  # GET_DATA_RSP
                return None
            
            payload = b''
            if data_len > 0 and len(data) >= 12 + data_len:
                payload = data[12:12+data_len]
            
            return {
                'source': source,
                'dest': dest,
                'cmd': cmd,
                'payload': payload
            }
        except:
            return None
    
    def convert_temperature(self, raw_bytes: bytes) -> Optional[float]:
        """Конвертация температуры"""
        if len(raw_bytes) < 2:
            return None
        try:
            raw_value = struct.unpack('<h', raw_bytes)[0]
            return raw_value / 10.0
        except:
            return None
    
    async def read_variable(self, device_addr: int, var_index: int, var_name: str) -> Optional[float]:
        """Чтение переменной"""
        if not self.ser or not self.ser.is_open:
            return None
        
        try:
            request = self.create_get_data_request(device_addr, var_index, 2)
            self.ser.write(request)
            self.real_data["gateway"]["packets_sent"] += 1
            
            await asyncio.sleep(0.3)
            
            if self.ser.in_waiting > 0:
                response_data = self.ser.read(self.ser.in_waiting)
                self.real_data["gateway"]["packets_received"] += 1
                
                response = self.parse_response(response_data)
                if response and len(response['payload']) >= 4:
                    temp_bytes = response['payload'][2:4]
                    value = self.convert_temperature(temp_bytes)
                    
                    if value is not None:
                        # Обновляем данные устройства
                        device_key = str(device_addr)
                        self.real_data["devices"][device_key]["status"] = "online"
                        self.real_data["devices"][device_key]["last_seen"] = datetime.now().isoformat()
                        self.real_data["devices"][device_key]["variables"][var_name] = {
                            "value": value,
                            "unit": "°C" if "Temperature" in var_name else "%",
                            "timestamp": datetime.now().isoformat(),
                            "index": var_index
                        }
                        
                        self.logger.info(f"📊 {var_name} (устройство {device_addr}): {value:.1f}")
                        return value
            
            # Нет ответа
            device_key = str(device_addr)
            if self.real_data["devices"][device_key]["status"] != "offline":
                self.real_data["devices"][device_key]["status"] = "no_response"
            
        except Exception as e:
            self.logger.error(f"Ошибка чтения {var_name}: {e}")
        
        return None
    
    async def collect_all_data(self):
        """Сбор всех данных"""
        self.logger.info("🔄 Сбор данных с KL-6400...")
        
        # Определяем переменные для чтения
        variables_to_read = [
            # Устройство 1 - основной контроллер
            (1, 100, "OutsideTemperature"),
            (1, 102, "InsideTemperature"),
            (1, 104, "OutsideHumidity"),
            (1, 106, "InsideHumidity"),
            (1, 108, "TargetTemperature"),
            
            # Устройство 2 - комната
            (2, 200, "RoomTemperature"),
            (2, 202, "RoomHumidity"),
            (2, 204, "RoomTargetTemp"),
            
            # Устройство 3 - неизвестный модуль
            (3, 300, "UnknownData1"),
            (3, 302, "UnknownData2")
        ]
        
        for device_addr, var_index, var_name in variables_to_read:
            await self.read_variable(device_addr, var_index, var_name)
            await asyncio.sleep(0.1)  # Небольшая пауза между запросами
        
        self.real_data["gateway"]["last_update"] = datetime.now()
        self.logger.info("✅ Цикл сбора данных завершен")
    
    def get_data(self) -> Dict:
        """Получение текущих данных"""
        # Обновляем время работы
        uptime = datetime.now() - self.real_data["gateway"]["uptime_start"]
        self.real_data["gateway"]["uptime"] = str(uptime).split('.')[0]  # Убираем микросекунды
        
        return self.real_data.copy()


class RealDataWebInterface:
    """
    Веб-интерфейс с реальными данными
    """
    
    def __init__(self, port: str):
        self.app = FastAPI(title="Stienen KL-6400 Real Monitor")
        self.collector = RealDataCollector(port)
        self.setup_routes()
        self.setup_middleware()
        
        # Фоновая задача сбора данных
        self.collection_task = None
        
    def setup_middleware(self):
        """Настройка middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def setup_routes(self):
        """Настройка маршрутов"""
        
        @self.app.on_event("startup")
        async def startup():
            """Запуск фоновых задач"""
            await self.start_data_collection()
        
        @self.app.on_event("shutdown") 
        async def shutdown():
            """Остановка фоновых задач"""
            await self.stop_data_collection()
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Главная панель с реальными данными"""
            data = self.collector.get_data()
            return self.render_dashboard(data)
        
        @self.app.get("/api/status")
        async def get_status():
            """API статуса с реальными данными"""
            return JSONResponse(self.collector.get_data())
        
        @self.app.get("/api/devices")
        async def get_devices():
            """API устройств"""
            data = self.collector.get_data()
            return JSONResponse(data["devices"])
        
        @self.app.get("/api/collect")
        async def manual_collect():
            """Ручной сбор данных"""
            await self.collector.collect_all_data()
            return JSONResponse({"status": "collected", "data": self.collector.get_data()})
    
    async def start_data_collection(self):
        """Запуск сбора данных"""
        if not self.collector.connect():
            self.logger.error("Не удалось подключиться к RS485")
            return
        
        async def collection_loop():
            while True:
                try:
                    await self.collector.collect_all_data()
                    await asyncio.sleep(30)  # Собираем данные каждые 30 секунд
                except Exception as e:
                    self.logger.error(f"Ошибка сбора данных: {e}")
                    await asyncio.sleep(10)
        
        self.collection_task = asyncio.create_task(collection_loop())
        self.logger.info("🚀 Фоновый сбор данных запущен")
    
    async def stop_data_collection(self):
        """Остановка сбора данных"""
        if self.collection_task:
            self.collection_task.cancel()
        if self.collector.ser and self.collector.ser.is_open:
            self.collector.ser.close()
    
    def render_dashboard(self, data: Dict) -> str:
        """Рендер панели с реальными данными"""
        
        # Получаем данные устройств
        device1 = data["devices"]["1"]
        device2 = data["devices"]["2"] 
        device3 = data["devices"]["3"]
        gateway = data["gateway"]
        
        # Функция для безопасного получения значения
        def get_var(device, var_name, default="—"):
            var = device["variables"].get(var_name, {})
            if var:
                value = var.get("value", default)
                unit = var.get("unit", "")
                return f"{value:.1f}{unit}" if isinstance(value, (int, float)) else str(value)
            return default
        
        def get_status_color(status):
            colors = {
                "online": "#28a745",
                "offline": "#dc3545", 
                "unknown": "#ffc107",
                "no_response": "#fd7e14",
                "connected": "#28a745",
                "connecting": "#17a2b8"
            }
            return colors.get(status, "#6c757d")
        
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏭 KL-6400 РЕАЛЬНЫЕ ДАННЫЕ</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        
        .header {{ 
            background: rgba(255,255,255,0.95);
            color: #333; 
            padding: 30px; 
            border-radius: 15px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        
        .real-badge {{
            display: inline-block;
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }}
        
        .header h1 {{ 
            margin: 0; 
            font-size: 2.5em;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .stats {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
            gap: 20px; 
            margin-bottom: 30px;
        }}
        
        .stat-card {{ 
            background: rgba(255,255,255,0.95);
            padding: 25px; 
            border-radius: 15px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
        }}
        
        .stat-card h3 {{ 
            color: #667eea;
            margin: 0 0 15px 0; 
            font-size: 1.2em;
            border-bottom: 2px solid #eef;
            padding-bottom: 10px;
        }}
        
        .device-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .device-card {{
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        
        .device-header {{
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin: -20px -20px 20px -20px;
            text-align: center;
        }}
        
        .device-1 {{ background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%); }}
        .device-2 {{ background: linear-gradient(45deg, #43e97b 0%, #38f9d7 100%); }}
        .device-3 {{ background: linear-gradient(45deg, #fa709a 0%, #fee140 100%); }}
        
        .variable-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        
        .variable-item:last-child {{ border-bottom: none; }}
        
        .variable-name {{ font-weight: 500; color: #555; }}
        
        .variable-value {{
            font-size: 1.2em;
            font-weight: bold;
        }}
        
        .temperature {{ color: #e74c3c !important; }}
        .humidity {{ color: #3498db !important; }}
        .status-value {{ font-weight: bold; }}
        
        .refresh-btn {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            border: none;
            border-radius: 50px;
            padding: 15px 25px;
            font-size: 16px;
            cursor: pointer;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }}
        
        .refresh-btn:hover {{
            transform: scale(1.05);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }}
        
        .timestamp {{
            text-align: center;
            color: rgba(255,255,255,0.8);
            margin-top: 20px;
            font-size: 0.9em;
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.8; transform: scale(1.02); }}
            100% {{ opacity: 1; transform: scale(1); }}
        }}
        
        .no-data {{ color: #888; font-style: italic; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏭 Stienen KL-6400 Monitor</h1>
            <span class="real-badge">🔴 РЕАЛЬНЫЕ ДАННЫЕ</span>
            <p>Прямое подключение к климатическому контроллеру</p>
            <p style="color: {get_status_color(gateway['status'])};">
                🟢 {gateway['status'].upper()} • {gateway['port']} • Время работы: {gateway.get('uptime', '—')}
            </p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3>📊 Статус гейтвея</h3>
                <div class="variable-item">
                    <span class="variable-name">Подключение:</span>
                    <span class="variable-value status-value" style="color: {get_status_color(gateway['status'])}">{gateway['status'].upper()}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Порт:</span>
                    <span class="variable-value">{gateway['port']}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Скорость:</span>
                    <span class="variable-value">{gateway['baudrate']} бод</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Время работы:</span>
                    <span class="variable-value">{gateway.get('uptime', '—')}</span>
                </div>
            </div>
            
            <div class="stat-card">
                <h3>📈 Статистика RS485</h3>
                <div class="variable-item">
                    <span class="variable-name">Устройств онлайн:</span>
                    <span class="variable-value">{len([d for d in data['devices'].values() if d['status'] == 'online'])}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Пакетов отправлено:</span>
                    <span class="variable-value">{gateway['packets_sent']}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Пакетов получено:</span>
                    <span class="variable-value">{gateway['packets_received']}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Последнее обновление:</span>
                    <span class="variable-value">{gateway.get('last_update', datetime.now()).strftime('%H:%M:%S') if isinstance(gateway.get('last_update'), datetime) else '—'}</span>
                </div>
            </div>
        </div>
        
        <div class="device-grid">
            <div class="device-card">
                <div class="device-header device-1">
                    <h3>🌡️ KL-6400 Controller (Адрес 1)</h3>
                    <p>Основной климатический контроллер</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">🌤️ Наружная температура:</span>
                    <span class="variable-value temperature">{get_var(device1, 'OutsideTemperature')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🏠 Внутренняя температура:</span>
                    <span class="variable-value temperature">{get_var(device1, 'InsideTemperature')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">💧 Наружная влажность:</span>
                    <span class="variable-value humidity">{get_var(device1, 'OutsideHumidity')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🎯 Заданная температура:</span>
                    <span class="variable-value temperature">{get_var(device1, 'TargetTemperature')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-value" style="color: {get_status_color(device1['status'])}">{device1['status'].upper()}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🕒 Последний ответ:</span>
                    <span class="variable-value">{device1['last_seen'][:19] if device1['last_seen'] else '—'}</span>
                </div>
            </div>
            
            <div class="device-card">
                <div class="device-header device-2">
                    <h3>🚪 Room Section (Адрес 2)</h3>
                    <p>Контроль комнаты/секции</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">🏠 Температура комнаты:</span>
                    <span class="variable-value temperature">{get_var(device2, 'RoomTemperature')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">💧 Влажность комнаты:</span>
                    <span class="variable-value humidity">{get_var(device2, 'RoomHumidity')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-value" style="color: {get_status_color(device2['status'])}">{device2['status'].upper()}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🕒 Последний ответ:</span>
                    <span class="variable-value">{device2['last_seen'][:19] if device2['last_seen'] else '—'}</span>
                </div>
            </div>
            
            <div class="device-card">
                <div class="device-header device-3">
                    <h3>❓ Unknown Module (Адрес 3)</h3>
                    <p>Дополнительный модуль</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">📊 Данные 1:</span>
                    <span class="variable-value">{get_var(device3, 'UnknownData1')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📊 Данные 2:</span>
                    <span class="variable-value">{get_var(device3, 'UnknownData2')}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-value" style="color: {get_status_color(device3['status'])}">{device3['status'].upper()}</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🕒 Последний ответ:</span>
                    <span class="variable-value">{device3['last_seen'][:19] if device3['last_seen'] else '—'}</span>
                </div>
            </div>
        </div>
        
        <div class="timestamp">
            🔴 ЖИВЫЕ ДАННЫЕ • Обновляется каждые 30 секунд • {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
    
    <button class="refresh-btn" onclick="location.reload()">
        🔄 Обновить
    </button>
    
    <script>
        // Автоматическое обновление каждые 30 секунд
        setInterval(function() {{
            location.reload();
        }}, 30000);
        
        console.log('🔴 KL-6400 Real Data Monitor загружен');
        console.log('📡 Прямое подключение к RS485');
        
        // Проверяем API статус
        setInterval(function() {{
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {{
                    console.log('📊 Обновление данных:', new Date().toLocaleTimeString());
                    console.log('Gateway:', data.gateway.status);
                    console.log('Devices online:', Object.values(data.devices).filter(d => d.status === 'online').length);
                }})
                .catch(console.error);
        }}, 30000);
    </script>
</body>
</html>
        """


def main():
    """Запуск веб-интерфейса с реальными данными"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Real Stienen Web Interface')
    parser.add_argument('command', nargs='?', default='web')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--rs485-port', default='/dev/tty.usbserial-210', help='RS485 port')
    
    args = parser.parse_args()
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Создаем веб-интерфейс с реальными данными
    web_interface = RealDataWebInterface(args.rs485_port)
    
    print(f"🔴 ЗАПУСК РЕАЛЬНОГО ВЕБ-ИНТЕРФЕЙСА KL-6400")
    print(f"=" * 50)
    print(f"   🌐 Web URL: http://localhost:{args.port}")
    print(f"   📡 RS485 порт: {args.rs485_port}")
    print(f"   🔄 Автосбор данных: каждые 30 секунд")
    print(f"   📊 Устройства: 1, 2, 3")
    print(f"")
    print(f"🎯 ОСОБЕННОСТИ:")
    print(f"   ✅ РЕАЛЬНЫЕ данные с KL-6400")
    print(f"   ✅ Прямое RS485 подключение") 
    print(f"   ✅ Автоматический опрос устройств")
    print(f"   ✅ Real-time обновления")
    print(f"   ✅ Мониторинг статуса устройств")
    print(f"")
    print(f"🚀 Открывайте: http://localhost:{args.port}")
    
    try:
        uvicorn.run(
            web_interface.app,
            host=args.host,
            port=args.port,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Завершение работы")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
