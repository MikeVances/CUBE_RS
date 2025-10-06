#!/usr/bin/env python3
"""
Модуль для работы с базой данных пользователей Telegram Bot
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


from core.config_manager import get_config


class TelegramBotDB:
    """Класс для работы с базой данных пользователей Telegram Bot"""

    def __init__(self, db_file: Optional[str] = None):
        # Use central config to resolve commands DB path
        cfg = get_config()
        self.db_file = db_file or cfg.database.commands_db

        # Создаем базу если не существует; затем всегда прогоняем миграции схемы
        if not Path(self.db_file).exists():
            logger.warning(f"⚠️ База данных {self.db_file} не найдена, создаем новую")
            self._create_database()
        # Обеспечиваем наличие всех таблиц/колонок (миграции при обновлении)
        try:
            self._ensure_schema()
        except Exception as e:
            logger.error(f"❌ Ошибка миграции схемы БД: {e}")

        logger.info(f"🗄️ Подключение к базе данных: {db_file}")

    def _create_database(self):
        """Создание базы данных и таблиц"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Таблица пользователей
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        telegram_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        access_level TEXT DEFAULT 'user',
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_command_at TIMESTAMP,
                        total_commands INTEGER DEFAULT 0
                    )
                """
                )

                # Таблица истории команд
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_command_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER,
                        command_type TEXT,
                        register_address TEXT,
                        success INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (telegram_id) REFERENCES telegram_users (telegram_id)
                    )
                """
                )

                # Таблица настроек доступа
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS access_config (
                        access_level TEXT PRIMARY KEY,
                        can_read INTEGER DEFAULT 1,
                        can_write INTEGER DEFAULT 0,
                        can_reset_alarms INTEGER DEFAULT 0,
                        allowed_registers TEXT,
                        commands_per_hour INTEGER DEFAULT 5
                    )
                """
                )

                # Вставляем базовые уровни доступа
                access_levels = [
                    ("user", 1, 0, 0, "[]", 5),
                    ("operator", 1, 0, 1, "[]", 20),
                    ("admin", 1, 1, 1, "[]", 50),
                    ("engineer", 1, 1, 1, "[]", 100),
                ]

                conn.executemany(
                    """
                    INSERT OR IGNORE INTO access_config
                    (access_level, can_read, can_write, can_reset_alarms, allowed_registers, commands_per_hour)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    access_levels,
                )

                # Таблица состояния чатов (master message, ACK/тихий режим)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_state (
                        chat_id INTEGER PRIMARY KEY,
                        last_message_id INTEGER,
                        ack_until TIMESTAMP
                    )
                    """
                )

                # Таблица приглашений
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_invitations (
                        invitation_code TEXT PRIMARY KEY,
                        invited_by INTEGER,
                        access_level TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        used_by INTEGER,
                        used_at TIMESTAMP,
                        is_active INTEGER DEFAULT 1,
                        FOREIGN KEY (invited_by) REFERENCES telegram_users (telegram_id),
                        FOREIGN KEY (used_by) REFERENCES telegram_users (telegram_id)
                    )
                    """
                )

                logger.info("✅ База данных создана")
        except Exception as e:
            logger.error(f"❌ Ошибка создания базы данных: {e}")
            raise

    # =======================
    # Состояние чатов / ACK
    # =======================
    def _ensure_schema(self) -> None:
        """Гарантирует наличие всех необходимых таблиц и колонок."""
        with sqlite3.connect(self.db_file) as conn:
            # Основные таблицы
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    access_level TEXT DEFAULT 'user',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_command_at TIMESTAMP,
                    total_commands INTEGER DEFAULT 0,
                    original_access_level TEXT,
                    temp_level_expires TIMESTAMP
                )
                """
            )
            # Приглашения
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_invitations (
                    invitation_code TEXT PRIMARY KEY,
                    invited_by INTEGER,
                    access_level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    used_by INTEGER,
                    used_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    command_type TEXT,
                    register_address TEXT,
                    success INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES telegram_users (telegram_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS access_config (
                    access_level TEXT PRIMARY KEY,
                    can_read INTEGER DEFAULT 1,
                    can_write INTEGER DEFAULT 0,
                    can_reset_alarms INTEGER DEFAULT 0,
                    allowed_registers TEXT,
                    commands_per_hour INTEGER DEFAULT 5
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    chat_id INTEGER PRIMARY KEY,
                    last_message_id INTEGER,
                    ack_until TIMESTAMP
                )
                """
            )

            # Базовые уровни доступа (idempotent)
            access_levels = [
                ("user", 1, 0, 0, "[]", 5),
                ("operator", 1, 0, 1, "[]", 20),
                ("admin", 1, 1, 1, "[]", 50),
                ("engineer", 1, 1, 1, "[]", 100),
            ]
            conn.executemany(
                """
                INSERT OR IGNORE INTO access_config
                (access_level, can_read, can_write, can_reset_alarms, allowed_registers, commands_per_hour)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                access_levels,
            )

            # Миграции колонок для telegram_users
            def ensure_column(table: str, col: str, decl: str):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

            ensure_column("telegram_users", "original_access_level", "TEXT")
            ensure_column("telegram_users", "temp_level_expires", "TIMESTAMP")

    def get_bot_state(self, chat_id: int) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                # На случай старой базы — создадим таблицу
                try:
                    row = conn.execute(
                        "SELECT * FROM bot_state WHERE chat_id=?", (chat_id,)
                    ).fetchone()
                except sqlite3.OperationalError:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS bot_state (
                            chat_id INTEGER PRIMARY KEY,
                            last_message_id INTEGER,
                            ack_until TIMESTAMP
                        )
                    """
                    )
                    row = conn.execute(
                        "SELECT * FROM bot_state WHERE chat_id=?", (chat_id,)
                    ).fetchone()
                return (
                    dict(row)
                    if row
                    else {
                        "chat_id": chat_id,
                        "last_message_id": None,
                        "ack_until": None,
                    }
                )
        except Exception as e:
            logger.error(f"❌ Ошибка чтения bot_state для чата {chat_id}: {e}")
            return {"chat_id": chat_id, "last_message_id": None, "ack_until": None}

    def set_last_message_id(self, chat_id: int, message_id: int) -> None:
        try:
            with sqlite3.connect(self.db_file) as conn:
                try:
                    conn.execute(
                        "INSERT INTO bot_state(chat_id,last_message_id) VALUES(?,?)\n"
                        "ON CONFLICT(chat_id) DO UPDATE SET last_message_id=excluded.last_message_id",
                        (chat_id, message_id),
                    )
                except sqlite3.OperationalError:
                    self._ensure_schema()
                    conn.execute(
                        "INSERT INTO bot_state(chat_id,last_message_id) VALUES(?,?)\n"
                        "ON CONFLICT(chat_id) DO UPDATE SET last_message_id=excluded.last_message_id",
                        (chat_id, message_id),
                    )
        except Exception as e:
            logger.error(f"❌ Ошибка записи last_message_id для чата {chat_id}: {e}")

    def set_ack_until(self, chat_id: int, minutes: int = 45) -> None:
        try:
            with sqlite3.connect(self.db_file) as conn:
                try:
                    conn.execute(
                        "INSERT INTO bot_state(chat_id,ack_until) VALUES(?, datetime('now', ?))\n"
                        "ON CONFLICT(chat_id) DO UPDATE SET ack_until=datetime('now', ?)",
                        (chat_id, f"+{minutes} minutes", f"+{minutes} minutes"),
                    )
                except sqlite3.OperationalError:
                    self._ensure_schema()
                    conn.execute(
                        "INSERT INTO bot_state(chat_id,ack_until) VALUES(?, datetime('now', ?))\n"
                        "ON CONFLICT(chat_id) DO UPDATE SET ack_until=datetime('now', ?)",
                        (chat_id, f"+{minutes} minutes", f"+{minutes} minutes"),
                    )
        except Exception as e:
            logger.error(f"❌ Ошибка записи ack_until для чата {chat_id}: {e}")

    def is_ack_active(self, chat_id: int) -> bool:
        try:
            with sqlite3.connect(self.db_file) as conn:
                row = conn.execute(
                    "SELECT ack_until FROM bot_state WHERE chat_id=?", (chat_id,)
                ).fetchone()
                if not row or not row[0]:
                    return False
                # Проверяем, не истёк ли ACK
                cur = conn.execute("SELECT datetime('now') < ?", (row[0],)).fetchone()
                return bool(cur and cur[0] == 1)
        except Exception as e:
            logger.error(f"❌ Ошибка проверки ACK для чата {chat_id}: {e}")
            return False

    def register_user(
        self,
        telegram_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        access_level: str = "user",
    ) -> bool:
        """Регистрация или обновление пользователя"""
        # Проверяем, является ли пользователь админом в ConfigManager
        try:
            from core.config_manager import get_config
            config = get_config()
            if telegram_id in config.telegram.admin_users:
                access_level = "admin"
                logger.info(f"🔑 Пользователь {telegram_id} автоматически получил права админа")
        except Exception as config_err:
            logger.warning(f"⚠️ Не удалось проверить права админа из конфигурации: {config_err}")
                
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Проверяем существует ли пользователь
                cursor = conn.execute(
                    "SELECT telegram_id FROM telegram_users WHERE telegram_id = ?",
                    (telegram_id,),
                )
                exists = cursor.fetchone()

                if exists:
                    # Обновляем существующего пользователя
                    conn.execute(
                        """
                        UPDATE telegram_users
                        SET username = ?, first_name = ?, last_name = ?,
                            last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """,
                        (username, first_name, last_name, telegram_id),
                    )

                    logger.info(f"👤 Пользователь {telegram_id} (@{username}) обновлён")
                else:
                    # Создаём нового пользователя
                    conn.execute(
                        """
                        INSERT INTO telegram_users
                        (telegram_id, username, first_name, last_name, access_level)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (telegram_id, username, first_name, last_name, access_level),
                    )

                    logger.info(
                        f"✅ Новый пользователь {telegram_id} (@{username}) зарегистрирован с уровнем {access_level}"
                    )

                return True

        except Exception as e:
            logger.error(f"❌ Ошибка регистрации пользователя {telegram_id}: {e}")
            return False

    def get_user(self, telegram_id: int) -> Optional[dict[str, Any]]:
        """Получение информации о пользователе"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM telegram_users WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователя {telegram_id}: {e}")
            return None

    def find_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        """Поиск пользователя по username (внутри класса)."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM telegram_users WHERE username = ?",
                    (username,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска пользователя @{username}: {e}")
            return None

    def get_user_access_level(self, telegram_id: int) -> str:
        """Получение уровня доступа пользователя"""
        try:
            user = self.get_user(telegram_id)
            return user.get("access_level", "user") if user else "user"
        except Exception as e:
            logger.error(f"❌ Ошибка получения уровня доступа {telegram_id}: {e}")
            return "user"

    def set_user_access_level(self, telegram_id: int, access_level: str) -> bool:
        """Изменение уровня доступа пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE telegram_users
                    SET access_level = ?, last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (access_level, telegram_id),
                )

                success = cursor.rowcount > 0
                if success:
                    logger.info(
                        f"🔧 Пользователь {telegram_id} получил уровень доступа: {access_level}"
                    )

                return success

        except Exception as e:
            logger.error(f"❌ Ошибка изменения уровня доступа {telegram_id}: {e}")
            return False

    def get_access_permissions(self, access_level: str) -> Optional[dict[str, Any]]:
        """Получение разрешений для уровня доступа"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM access_config WHERE access_level = ?
                """,
                    (access_level,),
                )

                row = cursor.fetchone()
                if row:
                    permissions = dict(row)
                    # Парсим JSON с разрешёнными регистрами
                    if permissions.get("allowed_registers"):
                        try:
                            permissions["allowed_registers"] = json.loads(
                                permissions["allowed_registers"]
                            )
                        except:
                            permissions["allowed_registers"] = []
                    return permissions
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения разрешений для {access_level}: {e}")
            return None

    def log_user_command(
        self,
        telegram_id: int,
        command_type: str,
        register_address: str = None,
        success: bool = True,
    ) -> bool:
        """Логирование команды пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    """
                    INSERT INTO user_command_history
                    (telegram_id, command_type, register_address, success)
                    VALUES (?, ?, ?, ?)
                """,
                    (telegram_id, command_type, register_address, success),
                )

                # Обновляем счётчики пользователя
                conn.execute(
                    """
                    UPDATE telegram_users
                    SET total_commands = total_commands + 1,
                        last_command_at = CURRENT_TIMESTAMP,
                        last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                return True

        except Exception as e:
            logger.error(f"❌ Ошибка логирования команды {telegram_id}: {e}")
            return False

    def get_user_command_count_last_hour(self, telegram_id: int) -> int:
        """Количество команд пользователя за последний час"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM user_command_history
                    WHERE telegram_id = ? AND timestamp > datetime('now', '-1 hour')
                """,
                    (telegram_id,),
                )

                return cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета команд {telegram_id}: {e}")
            return 0

    def get_user_stats(self, telegram_id: int) -> Optional[dict[str, Any]]:
        """Получение статистики пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Основная информация о пользователе
                cursor = conn.execute(
                    """
                    SELECT total_commands, last_command_at, created_at
                    FROM telegram_users WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                user_data = cursor.fetchone()
                if not user_data:
                    return None

                total_commands, last_command_at, created_at = user_data

                # Команды за последний час
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM user_command_history
                    WHERE telegram_id = ? AND timestamp > datetime('now', '-1 hour')
                """,
                    (telegram_id,),
                )
                commands_last_hour = cursor.fetchone()[0]

                # Команды за сегодня
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM user_command_history
                    WHERE telegram_id = ? AND date(timestamp) = date('now')
                """,
                    (telegram_id,),
                )
                commands_today = cursor.fetchone()[0]

                # Успешные команды
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM user_command_history
                    WHERE telegram_id = ? AND success = 1
                """,
                    (telegram_id,),
                )
                successful_commands = cursor.fetchone()[0]

                return {
                    "total_commands": total_commands or 0,
                    "commands_last_hour": commands_last_hour,
                    "commands_today": commands_today,
                    "successful_commands": successful_commands,
                    "success_rate": (successful_commands / max(total_commands, 1)) * 100
                    if total_commands
                    else 0,
                    "last_command_at": last_command_at,
                    "member_since": created_at,
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики {telegram_id}: {e}")
            return None

    def get_all_users(self) -> list[dict[str, Any]]:
        """Получение списка всех пользователей"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT telegram_id, username, first_name, last_name,
                           access_level, is_active, created_at, last_active
                    FROM telegram_users
                    ORDER BY last_active DESC
                """
                )

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка пользователей: {e}")
            return []

    def deactivate_user(self, telegram_id: int) -> bool:
        """Деактивация пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE telegram_users
                    SET is_active = 0, last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                success = cursor.rowcount > 0
                if success:
                    logger.info(f"🔒 Пользователь {telegram_id} деактивирован")

                return success

        except Exception as e:
            logger.error(f"❌ Ошибка деактивации пользователя {telegram_id}: {e}")
            return False

    def activate_user(self, telegram_id: int) -> bool:
        """Активация пользователя (обратная операция к deactivate)."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE telegram_users
                    SET is_active = 1, last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"🔓 Пользователь {telegram_id} активирован")
                return success
        except Exception as e:
            logger.error(f"❌ Ошибка активации пользователя {telegram_id}: {e}")
            return False

    def cleanup_old_history(self, days: int = 30) -> int:
        """Очистка старой истории команд"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # ❌ ИСПРАВЛЕНО: Безопасное SQL форматирование
                cursor = conn.execute(
                    """
                    DELETE FROM user_command_history
                    WHERE timestamp < datetime('now', ? || ' days')
                """,
                    (f"-{days}",),
                )

                deleted_count = cursor.rowcount
                logger.info(f"🧹 Удалено {deleted_count} старых записей истории команд")

                return deleted_count

        except Exception as e:
            logger.error(f"❌ Ошибка очистки истории: {e}")
            return 0


    def update_user_access_level(self, telegram_id: int, access_level: str) -> bool:
        """Обновление уровня доступа пользователя"""
        try:
            # Проверяем валидность уровня доступа
            valid_levels = ["user", "operator", "engineer", "admin"]
            if access_level not in valid_levels:
                logger.error(f"❌ Неверный уровень доступа: {access_level}")
                return False

            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE telegram_users
                    SET access_level = ?, last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (access_level, telegram_id),
                )

                success = cursor.rowcount > 0
                if success:
                    logger.info(
                        f"🔐 Уровень доступа пользователя {telegram_id} изменен на '{access_level}'"
                    )

                return success

        except Exception as e:
            logger.error(f"❌ Ошибка обновления уровня доступа {telegram_id}: {e}")
            return False

    def set_user_temporary_level(
        self, telegram_id: int, temp_level: str, duration_hours: int = 24
    ) -> bool:
        """Установка временного уровня доступа пользователя"""
        try:
            # Получаем текущий уровень доступа
            current_level = self.get_user_access_level(telegram_id)
            if not current_level:
                logger.error(f"❌ Пользователь {telegram_id} не найден")
                return False

            # Сохраняем оригинальный уровень и устанавливаем временный
            with sqlite3.connect(self.db_file) as conn:
                # Сначала сохраняем оригинальный уровень, если его еще нет
                conn.execute(
                    f"""
                    UPDATE telegram_users
                    SET original_access_level = COALESCE(original_access_level, access_level),
                        access_level = ?,
                        temp_level_expires = datetime('now', '+{duration_hours} hours'),
                        last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (temp_level, telegram_id),
                )

                logger.info(
                    f"🕐 Временный уровень '{temp_level}' установлен для пользователя {telegram_id} на {duration_hours}ч"
                )
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка установки временного уровня {telegram_id}: {e}")
            return False

    def restore_user_original_level(self, telegram_id: int) -> bool:
        """Восстановление оригинального уровня доступа пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE telegram_users
                    SET access_level = COALESCE(original_access_level, access_level),
                        original_access_level = NULL,
                        temp_level_expires = NULL,
                        last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                success = cursor.rowcount > 0
                if success:
                    logger.info(
                        f"🔄 Восстановлен оригинальный уровень доступа для пользователя {telegram_id}"
                    )

                return success

        except Exception as e:
            logger.error(f"❌ Ошибка восстановления уровня доступа {telegram_id}: {e}")
            return False

    def check_and_restore_expired_levels(self) -> int:
        """Проверка и восстановление истекших временных уровней доступа"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Находим пользователей с истекшими временными уровнями
                cursor = conn.execute(
                    """
                    SELECT telegram_id, username, access_level, original_access_level
                    FROM telegram_users
                    WHERE temp_level_expires IS NOT NULL
                    AND temp_level_expires < datetime('now')
                """
                )

                expired_users = cursor.fetchall()

                if expired_users:
                    # Восстанавливаем оригинальные уровни
                    conn.execute(
                        """
                        UPDATE telegram_users
                        SET access_level = COALESCE(original_access_level, access_level),
                            original_access_level = NULL,
                            temp_level_expires = NULL,
                            last_active = CURRENT_TIMESTAMP
                        WHERE temp_level_expires IS NOT NULL
                        AND temp_level_expires < datetime('now')
                    """
                    )

                    for user in expired_users:
                        logger.info(
                            f"⏰ Восстановлен уровень доступа для пользователя {user[0]} ({user[1]}): {user[2]} -> {user[3] or user[2]}"
                        )

                return len(expired_users)

        except Exception as e:
            logger.error(f"❌ Ошибка проверки истекших уровней: {e}")
            return 0

    def get_user_level_info(self, telegram_id: int) -> Optional[dict[str, Any]]:
        """Получение информации об уровне доступа пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT access_level, original_access_level, temp_level_expires
                    FROM telegram_users
                    WHERE telegram_id = ?
                """,
                    (telegram_id,),
                )

                row = cursor.fetchone()
                if row:
                    return {
                        "current_level": row["access_level"],
                        "original_level": row["original_access_level"],
                        "temp_expires": row["temp_level_expires"],
                        "is_temporary": row["original_access_level"] is not None,
                    }

                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об уровне {telegram_id}: {e}")
            return None

    def create_invitation(
        self, invited_by: int, access_level: str, hours_valid: int = 24
    ) -> str:
        """Создание приглашения с уникальным кодом"""
        try:
            import datetime
            import uuid

            # Генерируем уникальный код приглашения
            invitation_code = str(uuid.uuid4())[:8].upper()
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=hours_valid)

            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    """
                    INSERT INTO user_invitations
                    (invitation_code, invited_by, access_level, expires_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (invitation_code, invited_by, access_level, expires_at),
                )

                logger.info(
                    f"🔗 Создано приглашение {invitation_code} пользователем {invited_by}"
                )
                return invitation_code

        except Exception as e:
            logger.error(f"❌ Ошибка создания приглашения: {e}")
            return None

    def get_invitation(self, invitation_code: str) -> dict:
        """Получение информации о приглашении"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT i.*, u.username as invited_by_username, u.first_name as invited_by_name
                    FROM user_invitations i
                    LEFT JOIN telegram_users u ON i.invited_by = u.telegram_id
                    WHERE i.invitation_code = ?
                """,
                    (invitation_code,),
                )

                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"❌ Ошибка получения приглашения {invitation_code}: {e}")
            return None

    def use_invitation(self, invitation_code: str, user_id: int) -> bool:
        """Использование приглашения для регистрации"""
        try:

            with sqlite3.connect(self.db_file) as conn:
                # Проверяем, что приглашение активно и не истекло
                cursor = conn.execute(
                    """
                    SELECT * FROM user_invitations
                    WHERE invitation_code = ?
                    AND is_active = 1
                    AND used_by IS NULL
                    AND expires_at > datetime('now')
                """,
                    (invitation_code,),
                )

                invitation = cursor.fetchone()
                if not invitation:
                    return False

                # Отмечаем приглашение как использованное
                conn.execute(
                    """
                    UPDATE user_invitations
                    SET used_by = ?, used_at = CURRENT_TIMESTAMP, is_active = 0
                    WHERE invitation_code = ?
                """,
                    (user_id, invitation_code),
                )

                logger.info(
                    f"✅ Приглашение {invitation_code} использовано пользователем {user_id}"
                )
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка использования приглашения {invitation_code}: {e}")
            return False

    def get_user_invitations(self, user_id: int) -> list:
        """Получение списка приглашений, созданных пользователем"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT i.*, u.username as used_by_username, u.first_name as used_by_name
                    FROM user_invitations i
                    LEFT JOIN telegram_users u ON i.used_by = u.telegram_id
                    WHERE i.invited_by = ?
                    ORDER BY i.created_at DESC
                """,
                    (user_id,),
                )

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Ошибка получения приглашений пользователя {user_id}: {e}")
            return []

    def cleanup_expired_invitations(self) -> int:
        """Очистка истекших приглашений"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    """
                    UPDATE user_invitations
                    SET is_active = 0
                    WHERE expires_at < datetime('now') AND is_active = 1
                """
                )

                count = cursor.rowcount
                if count > 0:
                    logger.info(f"🗑️ Деактивировано {count} истекших приглашений")

                return count

        except Exception as e:
            logger.error(f"❌ Ошибка очистки истекших приглашений: {e}")
            return 0


# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================


def test_bot_database():
    """Тест функций базы данных"""
    print("🧪 Тестирование TelegramBotDB")
    print("=" * 40)

    try:
        # Используем тестовую базу
        test_db_file = "test_bot.db"
        if Path(test_db_file).exists():
            Path(test_db_file).unlink()

        db = TelegramBotDB(test_db_file)

        # Тест регистрации пользователя
        test_user_id = 123456789
        print(f"1. Тест регистрации пользователя {test_user_id}...")

        success = db.register_user(
            telegram_id=test_user_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )
        print(f"   Регистрация: {'✅' if success else '❌'}")

        # Тест получения пользователя
        print("2. Тест получения информации о пользователе...")
        user = db.get_user(test_user_id)
        if user:
            print(f"   ✅ Пользователь найден: @{user['username']}")
            print(f"   Уровень доступа: {user['access_level']}")
        else:
            print("   ❌ Пользователь не найден")

        # Тест логирования команд
        print("3. Тест логирования команд...")
        db.log_user_command(test_user_id, "read", None, True)
        db.log_user_command(test_user_id, "write", "0x0020", True)

        # Тест статистики
        print("4. Тест получения статистики...")
        stats = db.get_user_stats(test_user_id)
        if stats:
            print(f"   ✅ Всего команд: {stats.get('total_commands', 0)}")
            print(f"   За час: {stats.get('commands_last_hour', 0)}")
            print(f"   За сегодня: {stats.get('commands_today', 0)}")

        # Тест разрешений
        print("5. Тест получения разрешений...")
        permissions = db.get_access_permissions("user")
        if permissions:
            print(f"   ✅ Разрешения получены: can_read={permissions.get('can_read')}")

        print("\n✅ Все тесты базы данных пройдены!")

        # Удаляем тестовую базу
        Path(test_db_file).unlink()

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")


if __name__ == "__main__":
    test_bot_database()
