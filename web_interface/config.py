"""
Configuration for CUBE_RS Web Interface
"""

import os
from pathlib import Path
from typing import Optional


class WebConfig:
    """Web interface configuration"""
    
    # Server settings
    HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("WEB_PORT", "8080"))
    RELOAD: bool = os.getenv("WEB_RELOAD", "false").lower() == "true"
    
    # Gateway settings
    GATEWAY_HOST: str = os.getenv("GATEWAY_HOST", "127.0.0.1")
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "5023"))
    GATEWAY_DB_PATH: str = os.getenv("GATEWAY_DB_PATH", "web_modbus_data.db")
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "20"))
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    STATIC_DIR: Path = BASE_DIR / "static"
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))
    WS_RECONNECT_INTERVAL: int = int(os.getenv("WS_RECONNECT_INTERVAL", "3"))
    
    # Monitoring settings
    MONITORING_UPDATE_INTERVAL: int = int(os.getenv("MONITORING_UPDATE_INTERVAL", "2"))
    MAX_CHART_POINTS: int = int(os.getenv("MAX_CHART_POINTS", "20"))


# Global configuration instance
config = WebConfig()