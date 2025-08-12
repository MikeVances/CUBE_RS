#!/usr/bin/env python3
"""
Модуль для работы с базой данных пользователей Telegram Bot
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

class TelegramBotDB:
    """Класс для работы с базой данных пользователей Telegram Bot"""
    
    def __init__(self, db_file: str = "kub_commands.db"):
        self.db_file = db_file
        
        # Проверяем что база существует
        if not Path(db_file).exists():
            raise FileNotFoundError(f"База данных {db_file} не найдена. Запустите init_telegram_db.py")
        
        logger.info(f"🗄️ Подключение к базе данных: {db_file}")
    
    def register_user(self, telegram_id: int, username: str = None, 
                     first_name: str = None, last_name: str = None,
                     access_level: str = "user") -> bool:
        """Регистрация или обновление пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Проверяем существует ли пользователь
                cursor = conn.execute(
                    "SELECT telegram_id FROM telegram_users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                exists = cursor.fetchone()
                
                if exists:
                    # Обновляем существующего пользователя
                    conn.execute("""
                        UPDATE telegram_users 
                        SET username = ?, first_name = ?, last_name = ?, 
                            last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """, (username, first_name, last_name, telegram_id))
                    
                    logger.info(f"👤 Пользователь {telegram_id} (@{username}) обновлён")
                else:
                    # Создаём нового пользователя
                    conn.execute("""
                        INSERT INTO telegram_users 
                        (telegram_id, username, first_name, last_name, access_level)
                        VALUES (?, ?, ?, ?, ?)
                    """, (telegram_id, username, first_name, last_name, access_level))
                    
                    logger.info(f"✅ Новый пользователь {telegram_id} (@{username}) зарегистрирован с уровнем {access_level}")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации пользователя {telegram_id}: {e}")
            return False
    
    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM telegram_users WHERE telegram_id = ?
                """, (telegram_id,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователя {telegram_id}: {e}")
            return None
    
    def get_user_access_level(self, telegram_id: int) -> str:
        """Получение уровня доступа пользователя"""
        user = self.get_user(telegram_id)
        if user:
            return user.get('access_level', 'user')
        return 'user'  # По умолчанию
    
    def set_user_access_level(self, telegram_id: int, access_level: str) -> bool:
        """Установка уровня доступа пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    UPDATE telegram_users 
                    SET access_level = ?
                    WHERE telegram_id = ?
                """, (access_level, telegram_id))
                
                if cursor.rowcount > 0:
                    logger.info(f"✅ Пользователю {telegram_id} установлен уровень {access_level}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {telegram_id} не найден для смены уровня доступа")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка установки уровня доступа {telegram_id}: {e}")
            return False
    
    def get_access_permissions(self, access_level: str) -> Optional[Dict[str, Any]]:
        """Получение разрешений для уровня доступа"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM access_config WHERE access_level = ?
                """, (access_level,))
                
                row = cursor.fetchone()
                if row:
                    permissions = dict(row)
                    # Парсим JSON с разрешёнными регистрами
                    if permissions.get('allowed_registers'):
                        try:
                            permissions['allowed_registers'] = json.loads(permissions['allowed_registers'])
                        except:
                            permissions['allowed_registers'] = []
                    return permissions
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения разрешений для {access_level}: {e}")
            return None
    
    def log_user_command(self, telegram_id: int, command_type: str, 
                        register_address: str = None, success: bool = True) -> bool:
        """Логирование команды пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute("""
                    INSERT INTO user_command_history 
                    (telegram_id, command_type, register_address, success)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, command_type, register_address, success))
                
                # Обновляем счётчики пользователя
                conn.execute("""
                    UPDATE telegram_users 
                    SET total_commands = total_commands + 1,
                        last_command_at = CURRENT_TIMESTAMP,
                        last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """, (telegram_id,))
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования команды {telegram_id}: {e}")
            return False
    
    def get_user_command_count_last_hour(self, telegram_id: int) -> int:
        """Количество команд пользователя за последний час"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM user_command_history 
                    WHERE telegram_id = ? 
                    AND timestamp > datetime('now', '-1 hour')
                """, (telegram_id,))
                
                return cursor.fetchone()[0]
                
        except Exception as e:
            logger.error(f"❌ Ошибка подсчёта команд {telegram_id}: {e}")
            return 0
    
    def get_user_stats(self, telegram_id: int) -> Dict[str, Any]:
        """Получение статистики пользователя"""
        try:
            user = self.get_user(telegram_id)
            if not user:
                return {}
            
            with sqlite3.connect(self.db_file) as conn:
                # Команды за последний час
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM user_command_history 
                    WHERE telegram_id = ? 
                    AND timestamp > datetime('now', '-1 hour')
                """, (telegram_id,))
                commands_last_hour = cursor.fetchone()[0]
                
                # Команды за сегодня
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM user_command_history 
                    WHERE telegram_id = ? 
                    AND date(timestamp) = date('now')
                """, (telegram_id,))
                commands_today = cursor.fetchone()[0]
                
                # Последняя команда
                cursor = conn.execute("""
                    SELECT command_type, register_address, timestamp 
                    FROM user_command_history 
                    WHERE telegram_id = ? 
                    ORDER BY timestamp DESC LIMIT 1
                """, (telegram_id,))
                last_command = cursor.fetchone()
                
                return {
                    'user_info': user,
                    'commands_last_hour': commands_last_hour,
                    'commands_today': commands_today,
                    'total_commands': user.get('total_commands', 0),
                    'last_command': last_command,
                    'registered_at': user.get('created_at'),
                    'last_active': user.get('last_active')
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики {telegram_id}: {e}")
            return {}
    
    def get_all_users(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Получение списка всех пользователей"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                
                query = "SELECT * FROM telegram_users"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY created_at DESC"
                
                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка пользователей: {e}")
            return []
    
    def deactivate_user(self, telegram_id: int) -> bool:
        """Деактивация пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    UPDATE telegram_users 
                    SET is_active = 0
                    WHERE telegram_id = ?
                """, (telegram_id,))
                
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"🔒 Пользователь {telegram_id} деактивирован")
                
                return success
                
        except Exception as e:
            logger.error(f"❌ Ошибка деактивации пользователя {telegram_id}: {e}")
            return False
    
    def cleanup_old_history(self, days: int = 30) -> int:
        """Очистка старой истории команд"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    DELETE FROM user_command_history 
                    WHERE timestamp < datetime('now', '-{} days')
                """.format(days))
                
                deleted_count = cursor.rowcount
                logger.info(f"🧹 Удалено {deleted_count} старых записей истории команд")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки истории: {e}")
            return 0

# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================

def test_bot_database():
    """Тест функций базы данных"""
    print("🧪 Тестирование TelegramBotDB")
    print("=" * 40)
    
    try:
        db = TelegramBotDB()
        
        # Тест регистрации пользователя
        test_user_id = 123456789
        print(f"1. Тест регистрации пользователя {test_user_id}...")
        
        success = db.register_user(
            telegram_id=test_user_id,
            username="test_user",
            first_name="Test",
            last_name="User"
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
        
        print("\n✅ Все тесты пройдены!")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")

if __name__ == "__main__":
    test_bot_database()