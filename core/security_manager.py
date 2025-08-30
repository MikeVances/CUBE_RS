#!/usr/bin/env python3
"""
Менеджер безопасности для КУБ-1063 системы

Обеспечивает:
- Шифрование/дешифрование секретов
- Безопасное хранение токенов
- Управление ключами шифрования
- Аудит событий безопасности
"""

import os
import json
import base64
import hashlib
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logging.warning("⚠️ cryptography не установлена. Шифрование недоступно.")

logger = logging.getLogger(__name__)

class SecurityManager:
    """
    Менеджер безопасности системы КУБ-1063
    
    Функции:
    - Шифрование конфигов с секретами
    - Безопасное хранение токенов
    - Генерация и ротация ключей
    - Аудит событий безопасности
    - Контроль доступа к ресурсам
    """
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.secrets_dir = self.config_dir / "secrets"
        self.security_log = self.config_dir / "logs" / "security.log"
        
        # Создаем папки если не существуют
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        self.security_log.parent.mkdir(parents=True, exist_ok=True)
        
        # Настройка логирования безопасности
        self._setup_security_logging()
        
        # Инициализация шифрования
        self._encryption_key = None
        self._init_encryption()
    
    def _setup_security_logging(self):
        """Настройка специального логирования событий безопасности"""
        security_handler = logging.FileHandler(self.security_log, encoding='utf-8')
        security_handler.setFormatter(
            logging.Formatter('%(asctime)s [SECURITY] %(levelname)s - %(message)s')
        )
        
        self.security_logger = logging.getLogger('security')
        self.security_logger.setLevel(logging.INFO)
        self.security_logger.addHandler(security_handler)
    
    def _init_encryption(self):
        """Инициализация системы шифрования"""
        if not CRYPTO_AVAILABLE:
            self.security_logger.warning("Cryptography недоступна - работаем без шифрования")
            return
        
        # Проверяем существующий ключ шифрования
        key_file = self.secrets_dir / "master.key"
        
        if key_file.exists():
            try:
                self._load_master_key()
                self.security_logger.info("✅ Master key загружен")
            except Exception as e:
                self.security_logger.error(f"❌ Ошибка загрузки master key: {e}")
                self._generate_master_key()
        else:
            self._generate_master_key()
    
    def _generate_master_key(self):
        """Генерация нового мастер-ключа шифрования"""
        if not CRYPTO_AVAILABLE:
            return
            
        try:
            # Генерируем ключ из пароля и соли
            password = self._get_or_create_password()
            salt = os.urandom(16)
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            self._encryption_key = key
            
            # Сохраняем зашифрованный ключ
            key_data = {
                'salt': base64.b64encode(salt).decode(),
                'created_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            key_file = self.secrets_dir / "master.key"
            with open(key_file, 'w', encoding='utf-8') as f:
                json.dump(key_data, f, indent=2)
            
            # Устанавливаем безопасные права доступа
            os.chmod(key_file, 0o600)
            
            self.security_logger.info("✅ Новый master key создан и сохранен")
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка создания master key: {e}")
            raise
    
    def _load_master_key(self):
        """Загрузка существующего мастер-ключа"""
        if not CRYPTO_AVAILABLE:
            return
            
        key_file = self.secrets_dir / "master.key"
        
        with open(key_file, 'r', encoding='utf-8') as f:
            key_data = json.load(f)
        
        password = self._get_or_create_password()
        salt = base64.b64decode(key_data['salt'])
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        self._encryption_key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    
    def _get_or_create_password(self) -> str:
        """Получение пароля для шифрования"""
        # Приоритет источников пароля:
        # 1. Переменная окружения
        # 2. Файл с паролем (только для разработки!)
        # 3. Интерактивный ввод
        
        # 1. Переменная окружения
        password = os.getenv('CUBE_MASTER_PASSWORD')
        if password:
            return password
        
        # 2. Файл с паролем (НЕ для продакшена!)
        password_file = self.secrets_dir / "dev_password.txt"
        if password_file.exists():
            self.security_logger.warning("⚠️ Используется пароль из dev_password.txt - НЕ для продакшена!")
            return password_file.read_text().strip()
        
        # 3. Для разработки создаем простой пароль
        dev_password = "CUBE_RS_DEV_2023_SECURE"
        
        # Сохраняем для последующих запусков (только разработка!)
        with open(password_file, 'w', encoding='utf-8') as f:
            f.write(dev_password)
        os.chmod(password_file, 0o600)
        
        self.security_logger.warning("⚠️ Создан временный пароль для разработки")
        return dev_password
    
    def encrypt_data(self, data: Union[str, dict]) -> str:
        """Шифрование данных"""
        if not CRYPTO_AVAILABLE or not self._encryption_key:
            self.security_logger.warning("⚠️ Шифрование недоступно - возвращаем исходные данные")
            return json.dumps(data) if isinstance(data, dict) else data
        
        try:
            cipher = Fernet(self._encryption_key)
            
            if isinstance(data, dict):
                data_str = json.dumps(data)
            else:
                data_str = str(data)
            
            encrypted = cipher.encrypt(data_str.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка шифрования: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: str) -> Union[str, dict]:
        """Дешифрование данных"""
        if not CRYPTO_AVAILABLE or not self._encryption_key:
            try:
                # Попытка интерпретировать как JSON
                return json.loads(encrypted_data)
            except:
                return encrypted_data
        
        try:
            cipher = Fernet(self._encryption_key)
            
            encrypted_bytes = base64.b64decode(encrypted_data)
            decrypted = cipher.decrypt(encrypted_bytes)
            decrypted_str = decrypted.decode('utf-8')
            
            # Попытка интерпретировать как JSON
            try:
                return json.loads(decrypted_str)
            except:
                return decrypted_str
                
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка дешифрования: {e}")
            raise
    
    def save_encrypted_config(self, config_name: str, config_data: dict):
        """Сохранение зашифрованного конфига"""
        try:
            encrypted_data = self.encrypt_data(config_data)
            
            config_file = self.secrets_dir / f"{config_name}.enc"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'encrypted': True,
                    'data': encrypted_data,
                    'created_at': datetime.now().isoformat(),
                    'version': '1.0'
                }, f, indent=2)
            
            os.chmod(config_file, 0o600)
            self.security_logger.info(f"✅ Конфиг {config_name} зашифрован и сохранен")
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка сохранения зашифрованного конфига {config_name}: {e}")
            raise
    
    def load_encrypted_config(self, config_name: str) -> dict:
        """Загрузка зашифрованного конфига"""
        try:
            config_file = self.secrets_dir / f"{config_name}.enc"
            
            if not config_file.exists():
                raise FileNotFoundError(f"Зашифрованный конфиг {config_name} не найден")
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_wrapper = json.load(f)
            
            if not config_wrapper.get('encrypted', False):
                return config_wrapper.get('data', {})
            
            return self.decrypt_data(config_wrapper['data'])
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка загрузки зашифрованного конфига {config_name}: {e}")
            raise
    
    def migrate_plaintext_secrets(self, bot_secrets_file: str = "config/bot_secrets.json"):
        """Миграция открытых секретов в зашифрованный формат"""
        try:
            bot_secrets_path = Path(bot_secrets_file)
            
            if not bot_secrets_path.exists():
                self.security_logger.info(f"Файл {bot_secrets_file} не найден - нечего мигрировать")
                return
            
            # Читаем существующие секреты
            with open(bot_secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
            
            # Сохраняем зашифрованную версию
            self.save_encrypted_config('bot_secrets', secrets)
            
            # Создаем резервную копию оригинала
            backup_path = bot_secrets_path.with_suffix('.json.backup')
            bot_secrets_path.rename(backup_path)
            os.chmod(backup_path, 0o600)
            
            # Создаем заглушку для совместимости
            placeholder = {
                "telegram": {
                    "bot_token": "${TELEGRAM_BOT_TOKEN}",
                    "admin_users": "${CUBE_ADMIN_IDS}"
                },
                "_note": "Секреты перемещены в зашифрованный формат. См. config/secrets/bot_secrets.enc"
            }
            
            with open(bot_secrets_path, 'w', encoding='utf-8') as f:
                json.dump(placeholder, f, indent=2)
            
            self.security_logger.info(f"✅ Секреты мигрированы: {bot_secrets_file} -> config/secrets/bot_secrets.enc")
            print(f"✅ Секреты перемещены в зашифрованный файл")
            print(f"📁 Оригинал сохранен как: {backup_path}")
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка миграции секретов: {e}")
            raise
    
    def log_security_event(self, event_type: str, user_id: Optional[int] = None, 
                          details: Optional[Dict[str, Any]] = None, level: str = "INFO"):
        """Логирование событий безопасности"""
        event_data = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
        }
        
        if user_id:
            # Хешируем user ID для конфиденциальности в логах
            event_data['user_hash'] = hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
        
        if details:
            event_data['details'] = details
        
        log_message = f"{event_type} - {json.dumps(event_data, ensure_ascii=False)}"
        
        if level == "WARNING":
            self.security_logger.warning(log_message)
        elif level == "ERROR":
            self.security_logger.error(log_message)
        elif level == "CRITICAL":
            self.security_logger.critical(log_message)
        else:
            self.security_logger.info(log_message)
    
    def get_secure_config_value(self, config_name: str, key_path: str, fallback_env: str = None) -> Optional[str]:
        """Получение значения из зашифрованного конфига с fallback на переменные окружения"""
        try:
            # Сначала пробуем переменную окружения
            if fallback_env:
                env_value = os.getenv(fallback_env)
                if env_value:
                    return env_value
            
            # Затем зашифрованный конфиг
            config = self.load_encrypted_config(config_name)
            
            # Парсим путь к ключу (например: "telegram.bot_token")
            keys = key_path.split('.')
            value = config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            
            return value
            
        except Exception as e:
            self.security_logger.error(f"❌ Ошибка получения {key_path} из {config_name}: {e}")
            return None
    
    def health_check(self) -> Dict[str, Any]:
        """Проверка состояния системы безопасности"""
        health = {
            'encryption_available': CRYPTO_AVAILABLE,
            'master_key_exists': bool(self._encryption_key),
            'secrets_dir_exists': self.secrets_dir.exists(),
            'security_log_exists': self.security_log.exists(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Проверка прав доступа к критическим файлам
        critical_files = [
            'kub_commands.db',
            'kub_data.db',
            'config/bot_secrets.json'
        ]
        
        permissions_ok = True
        for file_path in critical_files:
            if Path(file_path).exists():
                stat = os.stat(file_path)
                mode = stat.st_mode & 0o777
                if mode != 0o600:  # Должно быть rw-------
                    permissions_ok = False
                    break
        
        health['file_permissions_secure'] = permissions_ok
        
        return health

# Глобальный экземпляр менеджера безопасности
_security_manager = None

def get_security_manager() -> SecurityManager:
    """Получение глобального менеджера безопасности (Singleton)"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager

def log_security_event(event_type: str, user_id: Optional[int] = None, 
                      details: Optional[Dict[str, Any]] = None, level: str = "INFO"):
    """Shortcut для логирования событий безопасности"""
    get_security_manager().log_security_event(event_type, user_id, details, level)

if __name__ == "__main__":
    # Тестирование SecurityManager
    print("🔒 Тестирование SecurityManager...")
    
    sm = get_security_manager()
    
    # Тест шифрования
    test_data = {"secret": "test_token_12345", "admin": 123456789}
    print(f"🔓 Исходные данные: {test_data}")
    
    if CRYPTO_AVAILABLE:
        encrypted = sm.encrypt_data(test_data)
        print(f"🔐 Зашифровано: {encrypted[:50]}...")
        
        decrypted = sm.decrypt_data(encrypted)
        print(f"🔓 Расшифровано: {decrypted}")
        
        print(f"✅ Шифрование работает: {test_data == decrypted}")
    else:
        print("⚠️ Установите cryptography для шифрования: pip install cryptography")
    
    # Проверка здоровья системы
    health = sm.health_check()
    print(f"🏥 Состояние безопасности: {health}")
    
    # Тест логирования
    sm.log_security_event("SYSTEM_TEST", user_id=12345, details={"test": True})
    print(f"📝 Событие записано в {sm.security_log}")
    
    print("✅ Тестирование завершено!")