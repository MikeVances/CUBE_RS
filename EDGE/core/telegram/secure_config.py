#!/usr/bin/env python3
"""
Модуль для безопасной загрузки конфигурации и секретов
"""

import getpass
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SecureConfig:
    """Класс для безопасной работы с конфигурацией и секретами"""

    def __init__(self):
        # config/ находится в корне проекта, а этот файл в telegram_bot/
        project_root = Path(__file__).parent.parent
        self.config_dir = project_root / "config"
        self.secrets_file = self.config_dir / "bot_secrets.json"
        self._token_cache = None

    def get_bot_token(self) -> Optional[str]:
        """Получение токена бота различными способами"""

        # Способ 1: Из кэша (если уже загружен)
        if self._token_cache:
            return self._token_cache

        # Способ 2: Из защищённого файла конфигурации
        token = self._load_token_from_file()
        if token:
            self._token_cache = token
            return token

        # Способ 3: Интерактивный ввод
        token = self._prompt_for_token()
        if token:
            # Предлагаем сохранить токен
            if self._ask_save_token():
                self._save_token_to_file(token)
            self._token_cache = token
            return token

        # Способ 4: Переменная окружения (последний вариант)
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if token:
            logger.warning("⚠️ Токен загружен из переменной окружения")
            self._token_cache = token
            return token

        return None

    def _load_token_from_file(self) -> Optional[str]:
        """Загрузка токена из защищённого файла"""
        try:
            if not self.secrets_file.exists():
                return None

            # Проверяем права доступа к файлу
            file_stat = self.secrets_file.stat()
            file_mode = oct(file_stat.st_mode)[-3:]

            if file_mode != "600":
                logger.warning(
                    f"⚠️ Файл {self.secrets_file} имеет небезопасные права доступа: {file_mode}"
                )

            with open(self.secrets_file, encoding="utf-8") as f:
                secrets = json.load(f)

            token = secrets.get("telegram", {}).get("bot_token")
            if token and token != "YOUR_BOT_TOKEN_HERE":
                logger.info("✅ Токен загружен из защищённого файла")
                return token

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла секретов: {e}")
            return None

    def _prompt_for_token(self) -> Optional[str]:
        """Интерактивный ввод токена"""
        print("\n🔑 БЕЗОПАСНЫЙ ВВОД ТОКЕНА БОТА")
        print("=" * 40)
        print("Токен не найден в конфигурации.")
        print("Получите токен у @BotFather в Telegram:")
        print("1. Напишите @BotFather")
        print("2. /newbot - создать нового бота")
        print("3. Скопируйте токен")
        print("\n(Ввод будет скрыт для безопасности)")

        try:
            token = getpass.getpass("🤖 Bot Token: ").strip()

            if not token:
                return None

            # Базовая валидация токена
            if not self._validate_token_format(token):
                print("❌ Неверный формат токена")
                return None

            return token

        except KeyboardInterrupt:
            print("\n❌ Ввод отменён")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка ввода токена: {e}")
            return None

    def _validate_token_format(self, token: str) -> bool:
        """Базовая проверка формата токена"""
        # Токен Telegram имеет формат: 123456789:ABC-DEF...
        parts = token.split(":")
        if len(parts) != 2:
            return False

        bot_id, secret = parts

        # Проверяем что ID бота - число
        if not bot_id.isdigit():
            return False

        # Проверяем длину секретной части
        if len(secret) < 30:
            return False

        return True

    def _ask_save_token(self) -> bool:
        """Спрашиваем пользователя о сохранении токена"""
        try:
            response = (
                input("\n💾 Сохранить токен в защищённом файле? (y/N): ").strip().lower()
            )
            return response in ["y", "yes", "да", "д"]
        except:
            return False

    def _save_token_to_file(self, token: str) -> bool:
        """Сохранение токена в защищённый файл"""
        try:
            # Создаём директорию если нужно
            self.config_dir.mkdir(exist_ok=True)

            # Создаём конфигурацию
            config = {
                "telegram": {"bot_token": token},
                "security": {"session_timeout": 3600},
            }

            # Сохраняем с безопасными правами
            with open(self.secrets_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Устанавливаем права доступа только для владельца
            os.chmod(self.secrets_file, 0o600)

            print(f"✅ Токен сохранён в {self.secrets_file}")
            print("🔒 Установлены безопасные права доступа (600)")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения токена: {e}")
            print(f"❌ Ошибка сохранения токена: {e}")
            return False
