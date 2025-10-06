#!/usr/bin/env python3
"""
Скрипт для безопасной миграции секретов в переменные окружения.
Перемещает секреты из файлов конфигурации в .env файл.
"""

import json
import os
import secrets
import sys
from pathlib import Path

# Добавляем корневой каталог в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.config_manager import get_config
    from core.security_manager import SecurityManager
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)


class SecretMigrator:
    """Класс для миграции секретов в переменные окружения."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self.config_dir = self.project_root / "config"
        self.secrets_dir = self.config_dir / "secrets"

    def migrate_secrets(self):
        """Основной метод миграции секретов."""
        print("🔐 Начинаю миграцию секретов в переменные окружения...")

        # Собираем секреты из разных источников
        secrets_data = {}

        # 1. Telegram bot secrets
        bot_secrets_file = self.config_dir / "bot_secrets.json"
        if bot_secrets_file.exists():
            try:
                with open(bot_secrets_file, encoding="utf-8") as f:
                    bot_secrets = json.load(f)
                    telegram_config = bot_secrets.get("telegram", {})

                    if "bot_token" in telegram_config:
                        secrets_data["TELEGRAM_BOT_TOKEN"] = telegram_config[
                            "bot_token"
                        ]

                    if "admin_users" in telegram_config:
                        admin_users = telegram_config["admin_users"]
                        if isinstance(admin_users, list):
                            secrets_data["TELEGRAM_ADMIN_USERS"] = ",".join(
                                map(str, admin_users)
                            )

                print(f"✅ Найдены Telegram секреты в {bot_secrets_file}")
            except Exception as e:
                print(f"⚠️ Ошибка чтения {bot_secrets_file}: {e}")

        # 2. Dev password
        dev_password_file = self.secrets_dir / "dev_password.txt"
        if dev_password_file.exists():
            try:
                with open(dev_password_file, encoding="utf-8") as f:
                    dev_password = f.read().strip()
                    if dev_password:
                        secrets_data["DEV_PASSWORD"] = dev_password
                print(f"✅ Найден dev password в {dev_password_file}")
            except Exception as e:
                print(f"⚠️ Ошибка чтения {dev_password_file}: {e}")

        # 3. Master key
        master_key_file = self.secrets_dir / "master.key"
        if master_key_file.exists():
            try:
                with open(master_key_file, encoding="utf-8") as f:
                    master_key = f.read().strip()
                    if master_key:
                        secrets_data["MASTER_KEY"] = master_key
                print(f"✅ Найден master key в {master_key_file}")
            except Exception as e:
                print(f"⚠️ Ошибка чтения {master_key_file}: {e}")

        # Генерируем новые секреты если нужно
        if "SECRET_KEY" not in secrets_data:
            secrets_data["SECRET_KEY"] = secrets.token_urlsafe(32)
            print("🔑 Сгенерирован новый SECRET_KEY")

        if "API_SECRET" not in secrets_data:
            secrets_data["API_SECRET"] = secrets.token_hex(32)
            print("🔑 Сгенерирован новый API_SECRET")

        # Добавляем стандартные настройки
        secrets_data.update(
            {
                "ENVIRONMENT": "development",
                "LOG_LEVEL": "INFO",
                "DEBUG": "false",
                "DATABASE_URL": "sqlite:///kub_data.db",
                "DATABASE_TIMEOUT": "5",
                "MODBUS_TCP_HOST": "127.0.0.1",
                "MODBUS_TCP_PORT": "502",
                "MODBUS_RTU_PORT": "/dev/ttyUSB0",
                "MODBUS_TIMEOUT": "3.0",
                "API_PORT": "8000",
                "CORS_ORIGINS": "https://localhost:3000,http://localhost:3000",
            }
        )

        # Создаем .env файл
        self.create_env_file(secrets_data)

        # Создаем бэкап существующих секретов
        self.backup_existing_secrets()

        print("✅ Миграция секретов завершена успешно!")
        print(f"📁 Файл .env создан: {self.env_file}")
        print("⚠️  ВАЖНО: Добавьте .env в .gitignore если еще не добавлен")
        print("🔐 После проверки работы системы удалите файлы секретов:")
        print(f"   - {bot_secrets_file}")
        print(f"   - {dev_password_file}")
        print(f"   - {master_key_file}")

    def create_env_file(self, secrets_data: dict):
        """Создает .env файл с секретами."""
        env_content = [
            "# CUBE_RS Environment Configuration",
            "# Этот файл содержит секреты - НЕ КОММИТЬТЕ ЕГО В GIT!",
            "",
            "# Security",
            f"SECRET_KEY={secrets_data.get('SECRET_KEY', '')}",
            f"MASTER_KEY={secrets_data.get('MASTER_KEY', '')}",
            f"DEV_PASSWORD={secrets_data.get('DEV_PASSWORD', '')}",
            f"API_SECRET={secrets_data.get('API_SECRET', '')}",
            "",
            "# Telegram Bot",
            f"TELEGRAM_BOT_TOKEN={secrets_data.get('TELEGRAM_BOT_TOKEN', '')}",
            f"TELEGRAM_ADMIN_USERS={secrets_data.get('TELEGRAM_ADMIN_USERS', '')}",
            "",
            "# Database",
            f"DATABASE_URL={secrets_data.get('DATABASE_URL', '')}",
            f"DATABASE_TIMEOUT={secrets_data.get('DATABASE_TIMEOUT', '')}",
            "",
            "# Modbus Configuration",
            f"MODBUS_TCP_HOST={secrets_data.get('MODBUS_TCP_HOST', '')}",
            f"MODBUS_TCP_PORT={secrets_data.get('MODBUS_TCP_PORT', '')}",
            f"MODBUS_RTU_PORT={secrets_data.get('MODBUS_RTU_PORT', '')}",
            f"MODBUS_TIMEOUT={secrets_data.get('MODBUS_TIMEOUT', '')}",
            "",
            "# System",
            f"ENVIRONMENT={secrets_data.get('ENVIRONMENT', '')}",
            f"LOG_LEVEL={secrets_data.get('LOG_LEVEL', '')}",
            f"DEBUG={secrets_data.get('DEBUG', '')}",
            "",
            "# API Gateway",
            f"API_PORT={secrets_data.get('API_PORT', '')}",
            f"CORS_ORIGINS={secrets_data.get('CORS_ORIGINS', '')}",
            "",
        ]

        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write("\n".join(env_content))

        # Устанавливаем права доступа только для владельца
        os.chmod(self.env_file, 0o600)

    def backup_existing_secrets(self):
        """Создает бэкап существующих секретов."""
        backup_dir = self.project_root / "backup_secrets"
        backup_dir.mkdir(exist_ok=True)

        files_to_backup = [
            self.config_dir / "bot_secrets.json",
            self.secrets_dir / "dev_password.txt",
            self.secrets_dir / "master.key",
        ]

        for source_file in files_to_backup:
            if source_file.exists():
                backup_file = backup_dir / source_file.name
                try:
                    import shutil

                    shutil.copy2(source_file, backup_file)
                    print(f"💾 Создан бэкап: {backup_file}")
                except Exception as e:
                    print(f"⚠️ Ошибка создания бэкапа {source_file}: {e}")

        # Создаем README в бэкапе
        readme_file = backup_dir / "README.md"
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write(
                """# Backup секретов

Этот каталог содержит бэкап секретов перед миграцией в переменные окружения.

## Безопасность
- Эти файлы содержат секретные данные
- Удалите этот каталог после подтверждения работы новой системы
- НЕ коммитьте эти файлы в git

## Восстановление
Если нужно восстановить старую систему, скопируйте файлы обратно:
- bot_secrets.json -> config/
- dev_password.txt -> config/secrets/
- master.key -> config/secrets/
"""
            )


def main():
    """Главная функция."""
    migrator = SecretMigrator()

    # Проверяем существует ли уже .env файл
    if migrator.env_file.exists():
        response = input(
            f"Файл {migrator.env_file} уже существует. Перезаписать? (y/N): "
        )
        if response.lower() not in ["y", "yes"]:
            print("Операция отменена.")
            return

    try:
        migrator.migrate_secrets()
    except KeyboardInterrupt:
        print("\n❌ Операция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
