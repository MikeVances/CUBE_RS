"""
WebSocket Server для CUBE RS
Передает данные с КУБ-1063 через WebSocket
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import logging
import websockets
import time
from modbus.modbus_storage import read_data

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.is_running = False
        
    async def register(self, websocket):
        """Регистрация нового клиента"""
        self.clients.add(websocket)
        logger.info(f"Новый клиент подключен. Всего клиентов: {len(self.clients)}")
        
    async def unregister(self, websocket):
        """Отключение клиента"""
        self.clients.remove(websocket)
        logger.info(f"Клиент отключен. Всего клиентов: {len(self.clients)}")
        
    async def send_data_to_clients(self, data):
        """Отправка данных всем подключенным клиентам"""
        # Добавляем поле day_counter, если оно есть в базе
        if "day_counter" not in data:
            try:
                from modbus.modbus_storage import read_data
                db_data = read_data()
                if "day_counter" in db_data:
                    data["day_counter"] = db_data["day_counter"]
            except Exception:
                pass
        if self.clients:
            message = json.dumps(data, ensure_ascii=False)
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )
            
    async def data_broadcast_loop(self):
        """Цикл отправки данных клиентам"""
        while self.is_running:
            try:
                data = read_data()
                if data:
                    await self.send_data_to_clients(data)
                    logger.info(f"Отправлены данные {len(self.clients)} клиентам")
                else:
                    logger.warning("Не удалось получить данные с устройства")
                    
                # Пауза между отправками
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле отправки данных: {e}")
                await asyncio.sleep(5)
                
    async def handle_client(self, websocket, path):
        """Обработка подключения клиента"""
        await self.register(websocket)
        try:
            async for message in websocket:
                # Обработка входящих сообщений от клиентов
                try:
                    data = json.loads(message)
                    logger.info(f"Получено сообщение от клиента: {data}")
                    
                    # Обработка команды "get"
                    if data.get("cmd") == "get":
                        current_data = read_data()
                        if current_data:
                            await websocket.send(json.dumps(current_data, ensure_ascii=False))
                            logger.info("Отправлены данные по запросу клиента")
                        
                except json.JSONDecodeError:
                    logger.warning(f"Получено некорректное JSON сообщение: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Соединение с клиентом закрыто")
        except Exception as e:
            logger.error(f"Ошибка обработки клиента: {e}")
        finally:
            await self.unregister(websocket)
            
    async def start_server(self):
        """Запуск WebSocket сервера"""
        try:
            server = await websockets.serve(
                self.handle_client,
                self.host,
                self.port
            )
            
            logger.info(f"🔌 WebSocket сервер запущен на ws://{self.host}:{self.port}")
            self.is_running = True
            
            # Запускаем цикл отправки данных в фоне
            asyncio.create_task(self.data_broadcast_loop())
            
            await server.wait_closed()
            
        except Exception as e:
            logger.error(f"Ошибка запуска WebSocket сервера: {e}")
            self.is_running = False

def run_websocket_server():
    """Функция для запуска WebSocket сервера в отдельном процессе"""
    server = WebSocketServer()
    
    while True:
        try:
            if not server.is_running:
                logger.info("Запуск WebSocket сервера...")
                asyncio.run(server.start_server())
            else:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Остановка WebSocket сервера по Ctrl+C")
            break
        except Exception as e:
            logger.error(f"Критическая ошибка в WebSocket сервере: {e}")
            time.sleep(10)  # Пауза перед повторной попыткой

if __name__ == "__main__":
    run_websocket_server() 