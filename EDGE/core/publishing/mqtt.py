"""
MQTT Publisher for CUBE RS
Публикует данные с КУБ устройств в MQTT-брокер с поддержкой multi-device архитектуры
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    mqtt = None

from ..device_registry import DeviceRegistry
from ..config_manager import get_config
from ..log_filter import get_secure_logger

logger = get_secure_logger(__name__)

class MQTTPublisher:
    """MQTT Publisher для данных КУБ устройств"""
    
    def __init__(self, device_registry: DeviceRegistry, config: Any = None):
        if not MQTT_AVAILABLE:
            raise ImportError("paho-mqtt не установлен. Установите: pip install paho-mqtt")
        
        self.device_registry = device_registry
        self.config = config or get_config()
        self.client = None
        self.is_connected = False
        self.is_running = False
        
        # Настройки из конфигурации или переменных окружения
        self.broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        self.broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        self.mqtt_topic_prefix = os.getenv('MQTT_TOPIC_PREFIX', 'cube_rs')
        self.publish_interval = int(os.getenv('MQTT_PUBLISH_INTERVAL', '10'))
        self.username = os.getenv('MQTT_USERNAME')  # опционально
        self.password = os.getenv('MQTT_PASSWORD')  # опционально
        
    def setup_client(self):
        """Настройка MQTT клиента"""
        if not MQTT_AVAILABLE:
            return False
            
        self.client = mqtt.Client()
        
        # Аутентификация если указана
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        
        # Обработчики событий
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        
        return True
    
    def _on_connect(self, client, userdata, flags, rc):
        """Обработчик подключения"""
        if rc == 0:
            self.is_connected = True
            logger.info(f"✅ Подключено к MQTT-брокеру {self.broker_host}:{self.broker_port}")
        else:
            self.is_connected = False
            error_messages = {
                1: "Неправильная версия протокола",
                2: "Недопустимый идентификатор клиента", 
                3: "Сервер недоступен",
                4: "Неправильный логин/пароль",
                5: "Не авторизован"
            }
            error_msg = error_messages.get(rc, f"Неизвестная ошибка: {rc}")
            logger.error(f"❌ Ошибка подключения к MQTT: {error_msg}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Обработчик отключения"""
        self.is_connected = False
        if rc == 0:
            logger.info("🔌 Отключено от MQTT-брокера")
        else:
            logger.warning(f"⚠️ Неожиданное отключение от MQTT: код {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Обработчик входящих сообщений"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.debug(f"📨 MQTT сообщение: {topic} -> {payload}")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки MQTT сообщения: {e}")
    
    def _on_publish(self, client, userdata, mid):
        """Обработчик успешной публикации"""
        logger.debug(f"📤 MQTT сообщение опубликовано: mid={mid}")
    
    def connect(self) -> bool:
        """Подключение к MQTT брокеру"""
        if not self.client:
            if not self.setup_client():
                return False
        
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # Ждем подключения до 5 секунд
            for _ in range(50):
                if self.is_connected:
                    return True
                time.sleep(0.1)
            
            logger.error("❌ Таймаут подключения к MQTT брокеру")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к MQTT: {e}")
            return False
    
    def disconnect(self):
        """Отключение от MQTT брокера"""
        if self.client and self.is_connected:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("🔌 Отключились от MQTT брокера")
    
    def publish_device_data(self, device_id: str, device_data: Dict[str, Any]) -> bool:
        """Публикация данных одного устройства"""
        if not self.is_connected:
            return False
        
        try:
            topic = f"{self.mqtt_topic_prefix}/{device_id}/data"
            
            # Добавляем метаданные
            message = {
                "device_id": device_id,
                "timestamp": time.time(),
                "data": device_data
            }
            
            payload = json.dumps(message, ensure_ascii=False)
            
            result = self.client.publish(topic, payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"📤 Данные {device_id} опубликованы в MQTT")
                return True
            else:
                logger.warning(f"⚠️ Ошибка публикации {device_id}: код {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка публикации данных {device_id}: {e}")
            return False
    
    def publish_all_devices(self) -> int:
        """Публикация данных всех устройств"""
        if not self.is_connected:
            return 0
        
        published_count = 0
        
        try:
            devices = self.device_registry.get_devices()
            
            for device_info in devices:
                device_data = self.device_registry.get_device_data(device_info.device_id)
                
                if device_data:
                    if self.publish_device_data(device_info.device_id, device_data):
                        published_count += 1
                    
        except Exception as e:
            logger.error(f"❌ Ошибка публикации всех устройств: {e}")
        
        if published_count > 0:
            logger.info(f"📤 Опубликованы данные {published_count} устройств в MQTT")
            
        return published_count
    
    async def publish_loop(self):
        """Основной цикл публикации данных"""
        logger.info(f"🚀 Запуск MQTT Publisher (интервал: {self.publish_interval}s)")
        
        if not self.connect():
            logger.error("❌ Не удалось подключиться к MQTT брокеру")
            return
        
        self.is_running = True
        
        try:
            while self.is_running:
                if self.is_connected:
                    published = self.publish_all_devices()
                    if published == 0:
                        logger.debug("📭 Нет данных для публикации")
                else:
                    logger.warning("⚠️ MQTT не подключен, попытка переподключения...")
                    self.connect()
                
                # Ждем следующий интервал
                await asyncio.sleep(self.publish_interval)
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в MQTT цикле: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Остановка MQTT Publisher"""
        logger.info("🛑 Остановка MQTT Publisher...")
        self.is_running = False
        self.disconnect()

# Функция для обратной совместимости
def publish_loop():
    """Legacy функция для обратной совместимости"""
    logger.warning("⚠️ Используется устаревшая функция publish_loop(). Используйте MQTTPublisher класс.")
    
    if not MQTT_AVAILABLE:
        logger.error("❌ paho-mqtt не установлен")
        return
    
    # Создаем простой publisher
    device_registry = DeviceRegistry()
    publisher = MQTTPublisher(device_registry)
    
    # Запускаем sync версию
    import threading
    
    def run_async():
        asyncio.run(publisher.publish_loop())
    
    thread = threading.Thread(target=run_async, daemon=False)
    thread.start()
    
    try:
        while thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Остановка MQTT Publisher...")
        publisher.stop()


if __name__ == "__main__":
    print("🚀 Запуск MQTT Publisher...")
    
    try:
        # Создаем Device Registry и Publisher
        device_registry = DeviceRegistry()
        publisher = MQTTPublisher(device_registry)
        
        # Запускаем асинхронный цикл
        asyncio.run(publisher.publish_loop())
        
    except KeyboardInterrupt:
        print("🛑 Остановлено пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
