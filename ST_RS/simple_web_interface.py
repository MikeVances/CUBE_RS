#!/usr/bin/env python3
"""
Simple Working Web Interface for Stienen Gateway
Простой рабочий веб-интерфейс для демонстрации данных
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


class SimpleWebInterface:
    """
    Простой веб-интерфейс для отображения данных гейтвея
    """
    
    def __init__(self):
        self.app = FastAPI(
            title="Stienen KL-6400 Monitor",
            description="Простой монитор для контроллера KL-6400"
        )
        self.setup_routes()
        self.setup_middleware()
        
        # Симулированные данные для демонстрации
        self.demo_data = {
            "devices": {
                "1": {
                    "name": "KL-6400 Controller", 
                    "address": 1,
                    "status": "online",
                    "last_seen": datetime.now().isoformat(),
                    "variables": {
                        "OutsideTemperature": {"value": 15.2, "unit": "°C", "timestamp": datetime.now().isoformat()},
                        "InsideTemperature": {"value": 22.8, "unit": "°C", "timestamp": datetime.now().isoformat()},
                        "OutsideHumidity": {"value": 65, "unit": "%", "timestamp": datetime.now().isoformat()},
                        "TargetTemperature": {"value": 21.0, "unit": "°C", "timestamp": datetime.now().isoformat()}
                    }
                },
                "2": {
                    "name": "Room Section", 
                    "address": 2,
                    "status": "online",
                    "last_seen": datetime.now().isoformat(),
                    "variables": {
                        "RoomTemperature": {"value": 20.5, "unit": "°C", "timestamp": datetime.now().isoformat()},
                        "RoomHumidity": {"value": 58, "unit": "%", "timestamp": datetime.now().isoformat()}
                    }
                },
                "3": {
                    "name": "Unknown Module", 
                    "address": 3,
                    "status": "online", 
                    "last_seen": datetime.now().isoformat(),
                    "variables": {
                        "UnknownData": {"value": 42, "unit": "", "timestamp": datetime.now().isoformat()}
                    }
                }
            },
            "gateway": {
                "name": "KL-6400 Gateway",
                "status": "running",
                "uptime": "0:05:30",
                "port": "/dev/tty.usbserial-210",
                "baudrate": 38400,
                "devices_count": 3,
                "packets_sent": 147,
                "packets_received": 98
            }
        }
    
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
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Главная панель"""
            return self.render_dashboard()
        
        @self.app.get("/api/status")
        async def get_status():
            """API статуса системы"""
            return JSONResponse(self.demo_data)
        
        @self.app.get("/api/devices")
        async def get_devices():
            """API списка устройств"""
            return JSONResponse(self.demo_data["devices"])
        
        @self.app.get("/api/devices/{device_id}")
        async def get_device(device_id: str):
            """API данных конкретного устройства"""
            device = self.demo_data["devices"].get(device_id)
            if device:
                return JSONResponse(device)
            else:
                return JSONResponse({"error": "Device not found"}, status_code=404)
    
    def render_dashboard(self) -> str:
        """Рендер главной панели"""
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏭 Stienen KL-6400 Monitor</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        
        .container {{ 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px;
        }}
        
        .header {{ 
            background: rgba(255,255,255,0.95);
            color: #333; 
            padding: 30px; 
            border-radius: 15px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
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
            background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin: -20px -20px 20px -20px;
            text-align: center;
        }}
        
        .variable-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        
        .variable-item:last-child {{
            border-bottom: none;
        }}
        
        .variable-name {{
            font-weight: 500;
            color: #555;
        }}
        
        .variable-value {{
            font-size: 1.2em;
            font-weight: bold;
            color: #667eea;
        }}
        
        .status-online {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .status-offline {{
            color: #dc3545;
            font-weight: bold;
        }}
        
        .refresh-btn {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(45deg, #667eea, #764ba2);
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
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
            100% {{ opacity: 1; }}
        }}
        
        .pulse {{ animation: pulse 2s infinite; }}
        
        .temperature {{
            font-size: 1.4em !important;
            color: #e74c3c !important;
        }}
        
        .humidity {{
            font-size: 1.4em !important;
            color: #3498db !important;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏭 Stienen KL-6400 Monitor</h1>
            <p>Система мониторинга климатического контроллера</p>
            <p class="pulse">🟢 Система активна • Подключено устройств: 3</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3>📊 Статус гейтвея</h3>
                <div class="variable-item">
                    <span class="variable-name">Название:</span>
                    <span class="variable-value">KL-6400 Gateway</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Статус:</span>
                    <span class="variable-value status-online">РАБОТАЕТ</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Порт:</span>
                    <span class="variable-value">/dev/tty.usbserial-210</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Скорость:</span>
                    <span class="variable-value">38400 бод</span>
                </div>
            </div>
            
            <div class="stat-card">
                <h3>📈 Статистика</h3>
                <div class="variable-item">
                    <span class="variable-name">Устройств:</span>
                    <span class="variable-value">3</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Пакетов отправлено:</span>
                    <span class="variable-value">147</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Пакетов получено:</span>
                    <span class="variable-value">98</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">Время работы:</span>
                    <span class="variable-value">5 мин</span>
                </div>
            </div>
        </div>
        
        <div class="device-grid">
            <div class="device-card">
                <div class="device-header">
                    <h3>🌡️ KL-6400 Controller (Адрес 1)</h3>
                    <p>Основной климатический контроллер</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">🌤️ Наружная температура:</span>
                    <span class="variable-value temperature">15.2°C</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🏠 Внутренняя температура:</span>
                    <span class="variable-value temperature">22.8°C</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">💧 Наружная влажность:</span>
                    <span class="variable-value humidity">65%</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🎯 Заданная температура:</span>
                    <span class="variable-value temperature">21.0°C</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-online">ОНЛАЙН</span>
                </div>
            </div>
            
            <div class="device-card">
                <div class="device-header">
                    <h3>🚪 Room Section (Адрес 2)</h3>
                    <p>Контроль комнаты/секции</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">🏠 Температура комнаты:</span>
                    <span class="variable-value temperature">20.5°C</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">💧 Влажность комнаты:</span>
                    <span class="variable-value humidity">58%</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-online">ОНЛАЙН</span>
                </div>
            </div>
            
            <div class="device-card">
                <div class="device-header">
                    <h3>❓ Unknown Module (Адрес 3)</h3>
                    <p>Дополнительный модуль</p>
                </div>
                
                <div class="variable-item">
                    <span class="variable-name">📊 Данные:</span>
                    <span class="variable-value">42</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">📡 Статус:</span>
                    <span class="variable-value status-online">ОНЛАЙН</span>
                </div>
                <div class="variable-item">
                    <span class="variable-name">🔍 Тип:</span>
                    <span class="variable-value">Требует идентификации</span>
                </div>
            </div>
        </div>
        
        <div class="timestamp">
            🕒 Последнее обновление: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
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
        
        console.log('🏭 Stienen KL-6400 Monitor загружен');
        console.log('🔄 Автообновление каждые 30 секунд');
        
        // Попытка получить реальные данные
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {{
                console.log('📊 Данные системы:', data);
            }})
            .catch(error => {{
                console.log('⚠️ Используются демо-данные');
            }});
    </script>
</body>
</html>
        """


def main():
    """Запуск простого веб-интерфейса"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple Stienen Web Interface')
    parser.add_argument('command', nargs='?', default='web', help='Command (web)')
    parser.add_argument('--port', type=int, default=8080, help='Port number')
    parser.add_argument('--host', default='0.0.0.0', help='Host address')
    parser.add_argument('--config', help='Config file (optional)')
    
    args = parser.parse_args()
    
    if args.command != 'web':
        print("Использование: python simple_web_interface.py web --port 8080")
        return
    
    # Создаем веб-интерфейс
    web_interface = SimpleWebInterface()
    
    print(f"🌐 Запуск Stienen KL-6400 Web Monitor")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   URL: http://localhost:{args.port}")
    print(f"")
    print(f"🎯 Особенности:")
    print(f"   ✅ Простой и надежный интерфейс")
    print(f"   ✅ Отображение данных KL-6400")
    print(f"   ✅ Автоматическое обновление")
    print(f"   ✅ Мобильная версия")
    print(f"   ✅ API для интеграции")
    print(f"")
    print(f"📡 Доступные API:")
    print(f"   GET /api/status - статус системы")
    print(f"   GET /api/devices - список устройств")
    print(f"   GET /api/devices/1 - данные устройства")
    print(f"")
    print(f"🚀 Открывайте браузер: http://localhost:{args.port}")
    
    try:
        # Запускаем сервер
        uvicorn.run(
            web_interface.app,
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n👋 Завершение работы веб-интерфейса")
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")


if __name__ == "__main__":
    main()
