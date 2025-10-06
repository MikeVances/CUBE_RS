"""
EDGE Publishing Module - Real-time data publishing
"""

from .websocket_server import WebSocketServer
# MQTT будет импортирован опционально из-за зависимости

__all__ = [
    'WebSocketServer'
]

# Опциональный импорт MQTT
try:
    from .mqtt import MQTTPublisher, publish_loop as mqtt_publish_loop
    __all__.extend(['MQTTPublisher', 'mqtt_publish_loop'])
except ImportError:
    MQTTPublisher = None
    mqtt_publish_loop = None