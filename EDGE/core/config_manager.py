#!/usr/bin/env python3
"""
Централизованный менеджер конфигурации для системы КУБ-1063

Обеспечивает единую точку доступа ко всем настройкам системы:
- Основные параметры системы
- RS485 настройки
- Modbus TCP порты
- Настройки базы данных
- Конфигурация Telegram бота
- Уровни доступа и безопасность
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import yaml
from dotenv import load_dotenv

from core.utils.paths import resolve_under_root

logger = logging.getLogger(__name__)

# Импорт SecurityManager для работы с секретами
try:
    from core.security_manager import get_security_manager

    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    logger.warning("⚠️ SecurityManager недоступен")


@dataclass
class RS485Config:
    """Конфигурация RS485 подключения"""

    port: str = "/dev/tty.usbserial-2130"
    baudrate: int = 9600
    parity: str = "N"
    databits: int = 8
    stopbits: int = 1
    timeout: float = 2.0
    slave_id: int = 1
    window_duration: int = 5
    cooldown_duration: int = 10


@dataclass
class ModbusTCPConfig:
    """Конфигурация Modbus TCP сервера"""

    port: int = 5023
    timeout: float = 3.0
    max_connections: int = 10


@dataclass
class DatabaseConfig:
    """Конфигурация базы данных"""

    file: str = "kub_data.db"
    commands_db: str = "kub_commands.db"
    timeout: int = 5
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"


@dataclass
class TelegramConfig:
    """Конфигурация Telegram бота"""

    token: Optional[str] = None
    admin_users: list = None
    default_access_level: str = "user"
    auto_register: bool = False
    rate_limit_commands_per_hour: int = 60
    max_message_length: int = 4000

    def __post_init__(self):
        if self.admin_users is None:
            self.admin_users = []


@dataclass
class SystemConfig:
    """Основные системные настройки"""

    environment: str = "development"  # development, production, testing
    log_level: str = "INFO"
    startup_timeout: int = 60
    shutdown_timeout: int = 15
    offline_mode: bool = False


@dataclass
class ServiceConfig:
    """Конфигурация сервисов"""

    gateway_enabled: bool = True
    dashboard_enabled: bool = True
    telegram_enabled: bool = True
    websocket_enabled: bool = False
    mqtt_enabled: bool = False

    dashboard_port: int = 8501
    websocket_port: int = 8765


@dataclass
class SecurityConfig:
    """Сетевые и доступные настройки безопасности"""

    cors_allowed_origins: List[str]
    require_health_token: bool
    health_token: Optional[str]


@dataclass
class AlarmRelayConfig:
    """Конфигурация аварийного реле для отображения в UI/боте"""

    enabled: bool = False
    register: str = "0x0082"  # один из 0x0081/0x0082/0x00A2 (цифровые выходы)
    bit: int = 7  # номер бита (0..15)
    label: str = "Реле аварии"


@dataclass
class SystemOutput:
    """Описатель выводимого релейного выхода (по биту цифрового слова)."""

    enabled: bool = False
    register: str = "0x0081"  # 0x0081/0x0082/0x00A2
    bit: int = 0  # 0..15
    label: str = "Выход"


class ConfigManager:
    """
    Централизованный менеджер всех конфигураций системы

    Загружает настройки из нескольких источников в порядке приоритета:
    1. Переменные окружения
    2. config/app_config.yaml (основные настройки)
    3. config/bot_secrets.json (токены и секреты)
    4. Значения по умолчанию
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)

        # Load environment variables from .env file if it exists
        load_dotenv()

        # Основные конфигурации
        self.rs485: RS485Config = RS485Config()
        self.modbus_tcp: ModbusTCPConfig = ModbusTCPConfig()
        self.database: DatabaseConfig = DatabaseConfig()
        self.telegram: TelegramConfig = TelegramConfig()
        self.system: SystemConfig = SystemConfig()
        self.services: ServiceConfig = ServiceConfig()
        self.security: SecurityConfig = SecurityConfig(
            cors_allowed_origins=["http://localhost", "http://127.0.0.1"],
            require_health_token=False,
            health_token=None,
        )
        self.alarm_relay: AlarmRelayConfig = AlarmRelayConfig()
        # Управляемые через конфиг элементы UI
        self.sensors: dict[str, bool] = {
            "temperature": True,
            "humidity": True,
            "co2": True,
            "nh3": False,
            "pressure": True,
        }
        self.system_outputs: list[SystemOutput] = []

        # Modbus регистры
        self.modbus_registers: dict[str, str] = {}

        # Менеджер безопасности
        self.security_manager = get_security_manager() if SECURITY_AVAILABLE else None

        self._load_configurations()
        self._normalize_database_paths()

    def _load_configurations(self):
        """Загрузка всех конфигураций"""
        try:
            # Загружаем основной конфиг
            self._load_main_config()

            # Загружаем секреты
            self._load_secrets()

            # Переопределяем из переменных окружения
            self._load_from_environment()

            # Валидация
            self._validate_config()

            logger.info("✅ Конфигурация загружена успешно")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            raise

    def _load_main_config(self):
        """Загрузка основного конфига из app_config.yaml"""
        config_file = self.config_dir / "app_config.yaml"

        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                # RS485
                if "rs485" in config_data:
                    rs485_data = config_data["rs485"]
                    for key, value in rs485_data.items():
                        if hasattr(self.rs485, key):
                            setattr(self.rs485, key, value)

                # Modbus TCP
                if "modbus_tcp" in config_data:
                    tcp_data = config_data["modbus_tcp"]
                    for key, value in tcp_data.items():
                        if hasattr(self.modbus_tcp, key):
                            setattr(self.modbus_tcp, key, value)

                # База данных
                if "database" in config_data:
                    db_data = config_data["database"]
                    for key, value in db_data.items():
                        if hasattr(self.database, key):
                            setattr(self.database, key, value)

                # Система
                if "system" in config_data:
                    sys_data = config_data["system"]
                    for key, value in sys_data.items():
                        if hasattr(self.system, key):
                            setattr(self.system, key, value)

                # Сервисы
                if "services" in config_data:
                    srv_data = config_data["services"]
                    for key, value in srv_data.items():
                        if hasattr(self.services, key):
                            setattr(self.services, key, value)

                # Аварийное реле (опционально)
                if "alarm_relay" in config_data:
                    ar = config_data["alarm_relay"] or {}
                    if isinstance(ar, dict):
                        for key in ["enabled", "register", "bit", "label"]:
                            if key in ar and hasattr(self.alarm_relay, key):
                                setattr(self.alarm_relay, key, ar[key])

                # Датчики (включение/отключение вывода)
                if "sensors" in config_data and isinstance(
                    config_data["sensors"], dict
                ):
                    for k, v in config_data["sensors"].items():
                        if isinstance(v, bool):
                            self.sensors[k] = v

                # Системные выходы (реле/группы вентиляторов)
                if "system_outputs" in config_data and isinstance(
                    config_data["system_outputs"], list
                ):
                    outputs = []
                    for item in config_data["system_outputs"]:
                        try:
                            so = SystemOutput(
                                enabled=bool(item.get("enabled", False)),
                                register=str(item.get("register", "0x0081")),
                                bit=int(item.get("bit", 0)),
                                label=str(item.get("label", "Выход")),
                            )
                            outputs.append(so)
                        except Exception:
                            continue
                    self.system_outputs = outputs

                # Modbus регистры
                if "modbus_registers" in config_data:
                    self.modbus_registers = config_data["modbus_registers"]

                logger.info(f"📁 Загружен основной конфиг: {config_file}")

            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки {config_file}: {e}")
        else:
            logger.info("📁 Создание app_config.yaml с настройками по умолчанию")
            self._create_default_config()

    def _normalize_database_paths(self) -> None:
        """Приводим пути баз данных к абсолютному виду внутри корня проекта."""
        try:
            self.database.file = resolve_under_root(self.database.file)
            self.database.commands_db = resolve_under_root(self.database.commands_db)
        except Exception as exc:
            logger.warning(f"⚠️ Не удалось нормализовать пути БД: {exc}")

    def _load_secrets(self):
        """Загрузка секретов через SecurityManager или из обычного файла"""
        # Пробуем загрузить из зашифрованного хранилища
        if self.security_manager:
            try:
                # Попытка загрузки зашифрованных секретов
                encrypted_secrets = self.security_manager.load_encrypted_config(
                    "bot_secrets"
                )
                self._process_telegram_secrets(encrypted_secrets)
                logger.info("🔐 Секреты загружены из зашифрованного хранилища")
                return
            except FileNotFoundError:
                # Зашифрованного файла нет, пробуем обычный
                pass
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки зашифрованных секретов: {e}")

        # Загрузка из обычного bot_secrets.json
        secrets_file = self.config_dir / "bot_secrets.json"

        if secrets_file.exists():
            try:
                with open(secrets_file, encoding="utf-8") as f:
                    secrets_data = json.load(f)

                self._process_telegram_secrets(secrets_data)
                logger.info(f"🔐 Секреты загружены из: {secrets_file}")

                # Предложение миграции в зашифрованный формат
                if self.security_manager and not self._is_placeholder_config(
                    secrets_data
                ):
                    logger.info(
                        "💡 Рекомендуется мигрировать секреты в зашифрованный формат"
                    )

            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки секретов: {e}")
        else:
            logger.warning("⚠️ bot_secrets.json не найден")

    def _process_telegram_secrets(self, secrets_data: dict):
        """Обработка секретов Telegram из любого источника"""
        if "telegram" in secrets_data:
            tg_data = secrets_data["telegram"]

            # Обрабатываем токен (может быть переменной окружения)
            if "bot_token" in tg_data:
                token = tg_data["bot_token"]
                if (
                    isinstance(token, str)
                    and token.startswith("${")
                    and token.endswith("}")
                ):
                    # Это переменная окружения
                    env_var = token[2:-1]  # Убираем ${ и }
                    token = os.getenv(env_var)
                self.telegram.token = token

            # Обрабатываем админов (может быть переменной окружения)
            if "admin_users" in tg_data:
                admin_users = tg_data["admin_users"]
                if (
                    isinstance(admin_users, str)
                    and admin_users.startswith("${")
                    and admin_users.endswith("}")
                ):
                    # Это переменная окружения
                    env_var = admin_users[2:-1]  # Убираем ${ и }
                    admin_str = os.getenv(env_var, "")
                    if admin_str:
                        admin_users = [
                            int(x.strip())
                            for x in admin_str.split(",")
                            if x.strip().isdigit()
                        ]
                    else:
                        admin_users = []
                self.telegram.admin_users = (
                    admin_users if isinstance(admin_users, list) else []
                )

            # Остальные настройки telegram
            for key in [
                "default_access_level",
                "auto_register",
                "rate_limit_commands_per_hour",
            ]:
                if key in tg_data:
                    setattr(self.telegram, key, tg_data[key])

    def _is_placeholder_config(self, secrets_data: dict) -> bool:
        """Проверка является ли конфиг заглушкой с переменными окружения"""
        tg_data = secrets_data.get("telegram", {})
        token = tg_data.get("bot_token", "")
        return isinstance(token, str) and token.startswith("${") and token.endswith("}")

    def migrate_secrets_to_encrypted(self):
        """Миграция секретов в зашифрованный формат"""
        if not self.security_manager:
            logger.warning("⚠️ SecurityManager недоступен - миграция невозможна")
            return False

        try:
            self.security_manager.migrate_plaintext_secrets()
            logger.info("✅ Секреты успешно мигрированы в зашифрованный формат")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка миграции секретов: {e}")
            return False

    def _load_from_environment(self):
        """Переопределение настроек из переменных окружения"""

        # Security
        secret_key = os.getenv("SECRET_KEY")
        if secret_key:
            logger.info("🔐 SECRET_KEY загружен из переменной окружения")

        master_key = os.getenv("MASTER_KEY")
        if master_key:
            logger.info("🔐 MASTER_KEY загружен из переменной окружения")

        # Telegram
        env_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if env_token:
            # По умолчанию НЕ перекрываем зашифрованный токен из ENC.
            # Разрешить перекрытие можно, задав TELEGRAM_ENV_OVERRIDE=true
            env_override = os.getenv("TELEGRAM_ENV_OVERRIDE", "false").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not self.telegram.token or env_override:
                self.telegram.token = env_token
                logger.info(
                    "🔐 Токен Telegram загружен из переменной окружения"
                    + (" (override)" if env_override else "")
                )
            else:
                logger.info(
                    "🔐 Токен Telegram в ENV обнаружен, но игнорируется (используется зашифрованный)"
                )

        edge_cors = os.getenv("EDGE_CORS_ALLOWED_ORIGINS")
        if edge_cors:
            origins = [origin.strip() for origin in edge_cors.split(",") if origin.strip()]
            if origins:
                self.security.cors_allowed_origins = origins
                logger.info(f"🌐 EDGE CORS origins из ENV: {origins}")

        health_token = os.getenv("EDGE_HEALTH_TOKEN")
        if health_token:
            self.security.health_token = health_token
            self.security.require_health_token = True
            logger.info("🔐 EDGE Health token загружен из ENV")

        require_health_token = os.getenv("EDGE_REQUIRE_HEALTH_TOKEN")
        if require_health_token:
            self.security.require_health_token = require_health_token.lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        # Database
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Parse SQLite URL format: sqlite:///path/to/db.db
            if database_url.startswith("sqlite:///"):
                db_path = database_url[10:]  # Remove sqlite:/// prefix
                self.database.file = db_path
                logger.info(f"💾 Database path установлен из ENV: {db_path}")

        database_timeout = os.getenv("DATABASE_TIMEOUT")
        if database_timeout:
            try:
                self.database.timeout = int(database_timeout)
                logger.info(f"⏱️ Database timeout: {self.database.timeout}s")
            except ValueError:
                logger.warning(f"⚠️ Неверный DATABASE_TIMEOUT: {database_timeout}")

        # Modbus
        modbus_tcp_host = os.getenv("MODBUS_TCP_HOST")
        if modbus_tcp_host:
            # Note: We don't have host in ModbusTCPConfig, add it if needed
            logger.info(f"🌐 Modbus TCP host: {modbus_tcp_host}")

        modbus_tcp_port = os.getenv("MODBUS_TCP_PORT")
        if modbus_tcp_port:
            try:
                self.modbus_tcp.port = int(modbus_tcp_port)
                logger.info(
                    f"🔌 Modbus TCP port установлен из ENV: {self.modbus_tcp.port}"
                )
            except ValueError:
                logger.warning(f"⚠️ Неверный MODBUS_TCP_PORT: {modbus_tcp_port}")

        modbus_rtu_port = os.getenv("MODBUS_RTU_PORT")
        if modbus_rtu_port:
            self.rs485.port = modbus_rtu_port
            logger.info(f"🔌 RS485 порт установлен из ENV: {modbus_rtu_port}")

        modbus_timeout = os.getenv("MODBUS_TIMEOUT")
        if modbus_timeout:
            try:
                timeout_val = float(modbus_timeout)
                self.rs485.timeout = timeout_val
                self.modbus_tcp.timeout = timeout_val
                logger.info(f"⏱️ Modbus timeout: {timeout_val}s")
            except ValueError:
                logger.warning(f"⚠️ Неверный MODBUS_TIMEOUT: {modbus_timeout}")

        # System settings
        env_environment = os.getenv("ENVIRONMENT", os.getenv("ENV"))
        if env_environment:
            self.system.environment = env_environment
            logger.info(f"🌍 Окружение: {env_environment}")

        env_log_level = os.getenv("LOG_LEVEL")
        if env_log_level:
            self.system.log_level = env_log_level.upper()
            logger.info(f"📊 Log level: {self.system.log_level}")

        debug = os.getenv("DEBUG", "false").lower()
        if debug in ("true", "1", "yes", "on"):
            self.system.log_level = "DEBUG"
            logger.info("🐛 Debug mode активирован")

        # API settings
        api_port = os.getenv("API_PORT")
        if api_port:
            try:
                # Store for use in API Gateway
                logger.info(f"🌐 API port из ENV: {api_port}")
            except ValueError:
                logger.warning(f"⚠️ Неверный API_PORT: {api_port}")

        cors_origins = os.getenv("CORS_ORIGINS")
        if cors_origins:
            # Store for use in CORS configuration
            logger.info(f"🌐 CORS origins из ENV: {cors_origins}")

        # Monitoring
        prometheus_port = os.getenv("PROMETHEUS_PORT")
        if prometheus_port:
            logger.info(f"📊 Prometheus port: {prometheus_port}")

        # External services
        vault_url = os.getenv("VAULT_URL")
        vault_token = os.getenv("VAULT_TOKEN")
        if vault_url and vault_token:
            logger.info("🔐 Vault configuration загружена из ENV")

    def _validate_config(self):
        """Валидация конфигурации"""
        errors = []

        # Проверка Telegram токена
        if self.telegram.token is None:
            errors.append("❌ Не найден TELEGRAM_BOT_TOKEN")

        # Проверка портов
        if not (1024 <= self.modbus_tcp.port <= 65535):
            errors.append(f"❌ Неверный порт gateway: {self.modbus_tcp.port}")

        # Проверка пути к RS485
        if not os.path.exists(self.rs485.port) and not self.rs485.port.startswith(
            "/dev/tty"
        ):
            logger.warning(f"⚠️ RS485 порт может быть недоступен: {self.rs485.port}")

        if errors:
            error_msg = "\n".join(errors)
            raise ValueError(f"Ошибки конфигурации:\n{error_msg}")

    def _create_default_config(self):
        """Создание файла конфигурации по умолчанию"""
        default_config = {
            "system": {
                "environment": "development",
                "log_level": "INFO",
                "startup_timeout": 60,
                "shutdown_timeout": 15,
                "offline_mode": False,
            },
            "rs485": {
                "port": "/dev/tty.usbserial-2130",
                "baudrate": 9600,
                "parity": "N",
                "databits": 8,
                "stopbits": 1,
                "timeout": 2.0,
                "slave_id": 1,
                "window_duration": 5,
                "cooldown_duration": 10,
            },
            "modbus_tcp": {"port": 5023, "timeout": 3.0, "max_connections": 10},
            "database": {
                "file": "kub_data.db",
                "commands_db": "kub_commands.db",
                "timeout": 5,
                "journal_mode": "WAL",
                "synchronous": "NORMAL",
            },
            "services": {
                "gateway_enabled": True,
                "dashboard_enabled": True,
                "telegram_enabled": True,
                "websocket_enabled": False,
                "mqtt_enabled": False,
                "dashboard_port": 8501,
                "websocket_port": 8765,
            },
            "modbus_registers": {
                "software_version": "0x0301",
                "digital_outputs_1": "0x0081",
                "digital_outputs_2": "0x0082",
                "digital_outputs_3": "0x00A2",
                "pressure": "0x0083",
                "humidity": "0x0084",
                "co2": "0x0085",
                "nh3": "0x0086",
                "grv_base": "0x0087",
                "grv_tunnel": "0x0088",
                "damper": "0x0089",
                "active_alarms": "0x00C3",
                "registered_alarms": "0x00C7",
                "active_warnings": "0x00CB",
                "registered_warnings": "0x00CF",
                "ventilation_target": "0x00D0",
                "ventilation_level": "0x00D1",
                "ventilation_scheme": "0x00D2",
                "day_counter": "0x00D3",
                "temp_target": "0x00D4",
                "temp_inside": "0x00D5",
                "temp_vent_activation": "0x00D6",
            },
        }

        config_file = self.config_dir / "app_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"📝 Создан файл конфигурации по умолчанию: {config_file}")

    def get_rs485_connection_params(self) -> dict[str, Any]:
        """Параметры подключения к RS485"""
        return {
            "port": self.rs485.port,
            "baudrate": self.rs485.baudrate,
            "parity": self.rs485.parity,
            "bytesize": self.rs485.databits,
            "stopbits": self.rs485.stopbits,
            "timeout": self.rs485.timeout,
        }

    def get_modbus_register(self, name: str) -> Optional[str]:
        """Получение адреса Modbus регистра по имени"""
        return self.modbus_registers.get(name)

    def get_all_modbus_registers(self) -> dict[str, str]:
        """Все Modbus регистры"""
        return self.modbus_registers.copy()

    def is_service_enabled(self, service_name: str) -> bool:
        """Проверка включен ли сервис"""
        return getattr(self.services, f"{service_name}_enabled", False)

    def get_service_port(self, service_name: str) -> int:
        """Порт сервиса"""
        if service_name == "gateway":
            return self.modbus_tcp.port
        elif service_name == "dashboard":
            return self.services.dashboard_port
        elif service_name == "websocket":
            return self.services.websocket_port
        else:
            raise ValueError(f"Неизвестный сервис: {service_name}")

    def reload(self):
        """Перезагрузка конфигурации"""
        logger.info("🔄 Перезагрузка конфигурации...")
        self._load_configurations()
        self._normalize_database_paths()

    def save_config(self):
        """Сохранение текущей конфигурации в файл"""
        config_data = {
            "system": {
                "environment": self.system.environment,
                "log_level": self.system.log_level,
                "startup_timeout": self.system.startup_timeout,
                "shutdown_timeout": self.system.shutdown_timeout,
                "offline_mode": self.system.offline_mode,
            },
            "rs485": {
                "port": self.rs485.port,
                "baudrate": self.rs485.baudrate,
                "parity": self.rs485.parity,
                "databits": self.rs485.databits,
                "stopbits": self.rs485.stopbits,
                "timeout": self.rs485.timeout,
                "slave_id": self.rs485.slave_id,
                "window_duration": self.rs485.window_duration,
                "cooldown_duration": self.rs485.cooldown_duration,
            },
            "modbus_tcp": {
                "port": self.modbus_tcp.port,
                "timeout": self.modbus_tcp.timeout,
                "max_connections": self.modbus_tcp.max_connections,
            },
            "database": {
                "file": self.database.file,
                "commands_db": self.database.commands_db,
                "timeout": self.database.timeout,
                "journal_mode": self.database.journal_mode,
                "synchronous": self.database.synchronous,
            },
            "services": {
                "gateway_enabled": self.services.gateway_enabled,
                "dashboard_enabled": self.services.dashboard_enabled,
                "telegram_enabled": self.services.telegram_enabled,
                "websocket_enabled": self.services.websocket_enabled,
                "mqtt_enabled": self.services.mqtt_enabled,
                "dashboard_port": self.services.dashboard_port,
                "websocket_port": self.services.websocket_port,
            },
            "modbus_registers": self.modbus_registers,
        }

        config_file = self.config_dir / "app_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"💾 Конфигурация сохранена в {config_file}")


# Глобальный экземпляр менеджера конфигурации
_config_manager = None


def get_config() -> ConfigManager:
    """Получение глобального менеджера конфигурации (Singleton)"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reload_config():
    """Перезагрузка конфигурации"""
    global _config_manager
    if _config_manager:
        _config_manager.reload()


# Удобные shortcuts для часто используемых настроек
def get_rs485_port() -> str:
    return get_config().rs485.port


def get_gateway_port() -> int:
    return get_config().modbus_tcp.port


def get_telegram_token() -> Optional[str]:
    return get_config().telegram.token


def get_telegram_admins() -> list:
    return get_config().telegram.admin_users


def get_database_file() -> str:
    return get_config().database.file


def get_commands_database_file() -> str:
    return get_config().database.commands_db


if __name__ == "__main__":
    # Тестирование конфиг-менеджера
    print("🔧 Тестирование ConfigManager...")

    config = get_config()

    print(f"📡 RS485 порт: {config.rs485.port}")
    print(f"🌐 Gateway порт: {config.modbus_tcp.port}")
    print(f"💾 База данных: {config.database.file}")
    print(f"🤖 Telegram админы: {len(config.telegram.admin_users)}")
    print(f"🏷️ Modbus регистров: {len(config.modbus_registers)}")

    print("✅ ConfigManager протестирован успешно!")
