import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

"""
MQTT Publisher for CUBE RS
Публикует данные с КУБ-1063 в MQTT-брокер
"""

import json
import logging
import time

import paho.mqtt.client as mqtt

from modbus.modbus_storage import read_data

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("mqtt.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Настройки брокера (вынесены в config.py)
BROKER_HOST = config.BROKER_HOST
BROKER_PORT = config.BROKER_PORT
MQTT_TOPIC = config.MQTT_TOPIC
PUBLISH_INTERVAL_SEC = 10     # частота публикации

def publish_loop():
    client = mqtt.Client()
    
    # Настройка обработчиков событий
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logging.info(f"✅ Подключено к MQTT-брокеру {config.BROKER_HOST}:{config.BROKER_PORT}")
        else:
            logging.error(f"❌ Ошибка подключения к MQTT: код {rc}")
    
    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logging.warning(f"⚠️  Отключение от MQTT брокера: код {rc}")
        else:
            logging.info("🔌 Отключено от MQTT брокера")
    
    def on_publish(client, userdata, mid):
        logging.debug(f"📤 Сообщение {mid} опубликовано")
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    try:
        if config.MQTT_USER and config.MQTT_PASS:
            client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
        
        logging.info(f"🔗 Подключение к MQTT-брокеру {config.BROKER_HOST}:{config.BROKER_PORT}...")
        client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)
        
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к MQTT: {e}")
        return

    client.loop_start()

    try:
        while True:
            try:
                data = read_data()
                if data:
                    # Преобразуем datetime в строку для JSON сериализации
                    if 'timestamp' in data and hasattr(data['timestamp'], 'isoformat'):
                        data['timestamp'] = data['timestamp'].isoformat()
                    
                    payload = json.dumps(data, ensure_ascii=False)
                    result = client.publish(config.MQTT_TOPIC, payload)
                    
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        logging.info(f"📤 Опубликовано в {config.MQTT_TOPIC}: {len(payload)} байт")
                    else:
                        logging.error(f"❌ Ошибка публикации: код {result.rc}")
                else:
                    logging.warning("⚠️  Нет данных для публикации")
                    
            except Exception as e:
                logging.error(f"❌ Ошибка чтения данных: {e}")
                
            time.sleep(PUBLISH_INTERVAL_SEC)
            
    except KeyboardInterrupt:
        logging.info("🛑 Остановка публикации по Ctrl+C")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    print("🚀 Запуск транслятора MQTT вручную...")
    publish_loop()