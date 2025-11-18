#!/usr/bin/env python3
"""
Telegram Bot для управления системой КУБ-1063
Использует централизованный конфиг-менеджер для всех настроек.
"""

import asyncio
import logging
import os
import sqlite3
import sys
import time
from typing import Optional


# Импорт централизованного конфиг-менеджера и безопасности
try:
    from core.config_manager import get_config
    from core.log_filter import setup_secure_logging
    from core.security_manager import log_security_event

    config = get_config()
    SECURITY_AVAILABLE = True
except ImportError as e:
    if "security_manager" in str(e) or "log_filter" in str(e):
        from core.config_manager import get_config

        config = get_config()
        SECURITY_AVAILABLE = False
        logging.warning(
            "⚠️ Модули безопасности недоступны - логирование безопасности отключено"
        )
    else:
        logging.error(
            "❌ Не удалось импортировать ConfigManager. Убедитесь что установлен PyYAML."
        )
        sys.exit(1)

from apps.edge.telegram_bot.bot_permissions import (
    check_command_rate_limit,
    check_user_permission,
)
from apps.edge.telegram_bot.bot_utils import (
    build_back_menu,
    build_confirmation_menu,
    build_main_menu,
    build_stats_menu,
    decode_active_alarms,
    error_message,
    format_sensor_data,
    format_extended_sensor_data,
    loading_message,
    send_typing_action,
    success_message,
    truncate_text,
    warning_message,
)

# Telegram Bot imports
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

# Наши модули
from .bot_database import TelegramBotDB

# Настройка логирования из конфига
log_file = config.config_dir / "logs" / "telegram.log"
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.system.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# КРИТИЧНО: Настройка безопасного логирования для предотвращения утечки токенов
if SECURITY_AVAILABLE:
    # Устанавливаем фильтр секретов для всех логгеров
    security_filter = setup_secure_logging()
    logger.info("🔐 Установлен фильтр безопасности для логов")
else:
    # Fallback: просто отключаем подробное логирование
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)


class KUBTelegramBot:
    """Telegram Bot для управления КУБ-1063 с централизованной конфигурацией"""

    def __init__(self, token: str):
        self.token = token
        self.config = config  # Используем глобальный конфиг-менеджер

        # НЕ создаем UnifiedKUBSystem - работаем через базы данных
        self.kub_system = None
        self.bot_db = TelegramBotDB()

        # Telegram Application
        self.application = None

        # Локальное состояние для уведомлений об авариях
        self._last_alarm_count = 0
        self._last_warning_count = 0
        self._last_alarm_notify_ts = 0
        # Оптимистичный режим после сброса: не больше 35 секунд показываем реле как ВЫКЛ
        self._optimistic_clear_until: dict[int, float] = {}
        # Управление звуковыми пингами
        self._sound_ping_delete_after = 25  # сек

        logger.info(
            f"✅ Загружено {len(self.config.telegram.admin_users)} администраторов"
        )
        logger.info("🤖 KUBTelegramBot с UX улучшениями инициализирован")

    # =======================================================================
    # РАБОТА С ДАННЫМИ ЧЕРЕЗ SQLite (вместо прямого RS485)
    # =======================================================================

    async def get_current_data_from_db(self):
        """Читаем текущие данные из SQLite (заполняется основной системой)"""
        try:
            import aiosqlite
            from core.config_manager import get_config
            from core.utils.paths import resolve_under_root
            db_path = get_config().database.file or "kub_data.db"
            db_path = resolve_under_root(db_path)

            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT temp_inside, temp_target, humidity, co2, nh3, pressure,
                           ventilation_level, ventilation_target, active_alarms,
                           active_warnings, updated_at,
                           digital_outputs_1, digital_outputs_2, digital_outputs_3
                    FROM latest_data WHERE id=1
                """
                )
                row = await cursor.fetchone()
                if row:
                    data = {
                        "temp_inside": row[0] if row[0] is not None else None,
                        "temp_target": row[1] if row[1] is not None else None,
                        "humidity": row[2] if row[2] is not None else None,
                        "co2": row[3] if row[3] is not None else None,
                        "nh3": row[4] if row[4] is not None else None,
                        "pressure": row[5] if row[5] is not None else None,
                        "ventilation_level": row[6] if row[6] is not None else None,
                        "ventilation_target": row[7] if row[7] is not None else None,
                        "active_alarms": row[8] if row[8] is not None else 0,
                        "active_warnings": row[9] if row[9] is not None else 0,
                        "updated_at": row[10],
                        "digital_outputs_1": row[11] if len(row) > 11 else None,
                        "digital_outputs_2": row[12] if len(row) > 12 else None,
                        "digital_outputs_3": row[13] if len(row) > 13 else None,
                        "connection_status": "connected" if row[10] else "disconnected",
                    }
                    # Вычисляем состояние аварийного реле по конфигурации, если включено
                    try:
                        ar = getattr(self.config, "alarm_relay", None)
                        if ar and getattr(ar, "enabled", False):
                            reg = str(getattr(ar, "register", "0x0082")).lower()
                            reg_to_key = {
                                "0x0081": "digital_outputs_1",
                                "0x0082": "digital_outputs_2",
                                "0x00a2": "digital_outputs_3",
                            }
                            key = reg_to_key.get(reg)
                            bit = int(getattr(ar, "bit", 7))
                            val = data.get(key) if key else None
                            if isinstance(val, int) and 0 <= bit <= 15:
                                data["alarm_relay"] = bool((val >> bit) & 1)
                                data["alarm_relay_label"] = getattr(
                                    ar, "label", "Реле аварии"
                                )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Ошибка вычисления состояния аварийного реле: {e}"
                        )
                    return data
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка чтения данных из БД: {e}")
            return None

    async def get_recent_sensor_recovery(self, minutes: int = 15) -> dict[str, bool]:
        """Проверяет за последние N минут: были ли пропадания показаний и затем восстановление.
        Возвращает словарь по датчикам: {'co2': True/False, 'humidity': ..., 'nh3': ...}
        """
        result = {"co2": False, "humidity": False, "nh3": False}
        try:
            import aiosqlite
            from core.config_manager import get_config
            from core.utils.paths import resolve_under_root
            db_path = get_config().database.file or "kub_data.db"
            db_path = resolve_under_root(db_path)

            async with aiosqlite.connect(db_path) as conn:
                conn.row_factory = aiosqlite.Row
                for field in ("co2", "humidity", "nh3"):
                    # Берем выборку за период, смотрим был ли None и затем последние значения не None
                    cursor = await conn.execute(
                        f"SELECT {field} as v FROM sensor_data WHERE timestamp > datetime('now', '-' || ? || ' minutes') ORDER BY timestamp ASC",
                        (minutes,),
                    )
                    rows = await cursor.fetchall()
                    if not rows:
                        continue
                    had_none = any(r["v"] is None for r in rows)
                    last_v = next((r["v"] for r in reversed(rows) if True), None)
                    if had_none and last_v is not None:
                        result[field] = True
        except Exception as e:
            logger.warning(f"⚠️ Ошибка анализа восстановления датчиков: {e}")
        return result

    # =======================
    # Оценка причин аварии и нейтрализации
    # =======================
    async def compute_alarm_assessment(self, data: dict[str, any]) -> dict[str, any]:
        """Возвращает оценку причин аварий и факта нейтрализации.
        Использует БИТЫ аварий (0x00C0–0x00C3) как первичный источник истины.
        Никаких уставок не записываем и не интерпретируем — если бит активен, причина АКТИВНА.
        Для сенсоров без битов (CO₂/NH₃) используем их статусы break/error.
        """
        result = {
            "items": [],  # [{title, neutralized(bool), details}]
            "all_neutralized": False,
        }
        try:
            mask = int(data.get("active_alarms", 0) or 0)
            humidity = data.get("humidity")
            hum_status = data.get("humidity_status")
            pressure_status = data.get("pressure_status")
            co2 = data.get("co2")
            co2_status = data.get("co2_status")
            nh3_status = data.get("nh3_status")

            # Сенсоры: обрывы/ошибки → нейтрализация, если status=ok (или было восстановление)
            recovery = await self.get_recent_sensor_recovery(minutes=15)

            def add(title: str, neutralized: bool, details: str):
                result["items"].append(
                    {
                        "title": title,
                        "neutralized": bool(neutralized),
                        "details": details,
                    }
                )

            # Температура высокая/низкая — только по битам: если бит активен, причина активна
            if ((mask >> 35) & 1) == 1:  # высокая внутр. температура
                add("Высокая внутренняя температура", False, "бит аварии активен")
            if ((mask >> 36) & 1) == 1 or (
                (mask >> 57) & 1
            ) == 1:  # низкая внутр. температура
                add("Низкая внутренняя температура", False, "бит аварии активен")

            # Влажность высокая
            if ((mask >> 37) & 1) == 1:
                add("Высокая влажность", False, f"статус={hum_status}, H={humidity}")

            # Давление высокое/низкое
            if ((mask >> 38) & 1) == 1:
                add(
                    "Высокое отрицательное давление", False, f"статус={pressure_status}"
                )
            if ((mask >> 39) & 1) == 1:
                add("Низкое отрицательное давление", False, f"статус={pressure_status}")

            # Обрывы датчиков
            if ((mask >> 40) & 1) == 1:
                ok = (hum_status == "ok") or recovery.get("humidity", False)
                add("Обрыв датчика влажности", ok, f"статус={hum_status}")
            if ((mask >> 41) & 1) == 1:
                ok = (pressure_status == "ok") or recovery.get("pressure", False)
                add(
                    "Обрыв датчика отрицательного давления",
                    ok,
                    f"статус={pressure_status}",
                )
            # Температуры T1/T2/Tнаруж — нет отдельных статусов, считаем по исчезновению бита (здесь proxy=False)
            if ((mask >> 42) & 1) == 1:
                add(
                    "Обрыв датчика внутренней температуры 1",
                    False,
                    "Оценка по показаниям датчика недоступна",
                )
            if ((mask >> 43) & 1) == 1:
                add(
                    "Обрыв датчика внутренней температуры 2",
                    False,
                    "Оценка по показаниям датчика недоступна",
                )
            if ((mask >> 44) & 1) == 1:
                add(
                    "Обрыв датчика наружной температуры",
                    False,
                    "Оценка по показаниям датчика недоступна",
                )

            # Сенсоры без битов — CO₂/NH₃: используем статусы
            if co2_status in ("break", "error"):
                ok = (co2_status == "ok") or recovery.get("co2", False)
                add("Ошибка/обрыв датчика CO₂", ok, f"статус={co2_status}")
            if nh3_status in ("break", "error"):
                ok = (nh3_status == "ok") or recovery.get("nh3", False)
                add("Ошибка/обрыв датчика NH₃", ok, f"статус={nh3_status}")

            # Итог: если список пуст (битов активных нет), но аварийное реле ВКЛ — можно предложить сброс
            if not result["items"] and (data.get("alarm_relay") is True):
                result["items"].append(
                    {
                        "title": "Аварийное реле активно",
                        "neutralized": False,
                        "details": "Причина не определена по данным",
                    }
                )

            # Считаем нейтрализовано по битам: если маска == 0 И нет сенсорных ошибок CO₂/NH₃
            sensor_errors = (co2_status in ("break", "error")) or (
                nh3_status in ("break", "error")
            )
            result["all_neutralized"] = (mask == 0) and not sensor_errors
            return result
        except Exception as e:
            logger.warning(f"⚠️ Ошибка оценки причин аварии: {e}")
            return result

    def add_write_command_to_db(self, register: int, value: int, user_info: str):
        """Добавляем команду записи в очередь (выполнит основная система)"""
        try:
            import sqlite3
            import uuid
            from datetime import datetime

            command_id = str(uuid.uuid4())[:8]

            from core.config_manager import get_config
            with sqlite3.connect(get_config().database.commands_db) as conn:
                conn.execute(
                    """
                    INSERT INTO write_commands
                    (id, register, value, user_info, created_at, status, priority)
                    VALUES (?, ?, ?, ?, ?, 'pending', 1)
                """,
                    (
                        command_id,
                        register,
                        value,
                        user_info,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()

            logger.info(
                f"📝 Команда записи добавлена: reg=0x{register:04X}, val={value}, id={command_id}"
            )
            return True, command_id

        except Exception as e:
            logger.error(f"❌ Ошибка добавления команды: {e}")
            return False, str(e)

    # =======================================================================
    # ОБРАБОТЧИКИ КОМАНД
    # =======================================================================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - обработка приглашений и защита от незарегистрированных пользователей"""
        user = update.effective_user

        # Логирование события безопасности
        if SECURITY_AVAILABLE:
            log_security_event(
                "BOT_START_ATTEMPT",
                user_id=user.id,
                details={
                    "username": user.username,
                    "first_name": user.first_name,
                    "has_args": bool(context.args),
                },
            )

        # Показываем печатание
        await send_typing_action(update, context)

        # Проверяем, есть ли приглашение в сообщении
        invitation_code = None
        if context.args:
            # Ищем код приглашения в формате invite_XXXXXXXX
            for arg in context.args:
                if arg.startswith("invite_"):
                    invitation_code = arg.replace("invite_", "")
                    break

        # Проверяем, зарегистрирован ли пользователь
        existing_user = self.bot_db.get_user(user.id)

        if existing_user:
            # Пользователь уже зарегистрирован - показываем главное меню
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            # Если есть активные аварии/реле – добавим кнопку ACK (тихий режим)
            try:
                alarms_cnt = int((data or {}).get("active_alarms", 0) or 0)
                relay_on = bool((data or {}).get("alarm_relay"))
                if alarms_cnt > 0 or relay_on:
                    from telegram import InlineKeyboardButton

                    kb = menu.inline_keyboard
                    kb.append(
                        [
                            InlineKeyboardButton(
                                "🤫 Тихий режим 45 мин", callback_data="ack_alarms"
                            )
                        ]
                    )
            except Exception:
                pass

            welcome_text = (
                f"👋 С возвращением, {user.first_name or user.username}!\n\n"
                f"<b>КУБ-1063 Control Bot</b>\n"
                f"🔐 Ваш уровень доступа: <b>{access_level}</b>\n\n"
                "Выберите действие в меню ниже ⬇️"
            )

            await update.message.reply_text(
                welcome_text, reply_markup=menu, parse_mode="HTML"
            )

            self.bot_db.log_user_command(user.id, "start", None, True)
            return

        # Новый пользователь - требуется приглашение
        if not invitation_code:
            # Нет приглашения - отклоняем доступ
            await update.message.reply_text(
                "🔒 <b>Доступ ограничен</b>\n\n"
                "Для использования бота необходимо приглашение.\n"
                "Обратитесь к администратору системы КУБ-1063 за ссылкой-приглашением.\n\n"
                "📋 <b>Как получить доступ:</b>\n"
                "1. Попросите администратора создать приглашение\n"
                "2. Перейдите по ссылке-приглашению\n"
                "3. Получите доступ к системе",
                parse_mode="HTML",
            )
            return

        # Есть код приглашения - проверяем его
        try:
            import datetime
            import sqlite3

            from core.config_manager import get_config
            conn = sqlite3.connect(get_config().database.commands_db)
            cursor = conn.cursor()

            # Ищем приглашение
            cursor.execute(
                """
                SELECT invitation_code, invited_by, access_level, expires_at, used_by
                FROM user_invitations
                WHERE invitation_code = ?
            """,
                (invitation_code,),
            )

            invitation = cursor.fetchone()

            if not invitation:
                conn.close()
                await update.message.reply_text(
                    "❌ <b>Недействительное приглашение</b>\n\n"
                    "Код приглашения не найден или устарел.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="HTML",
                )
                return

            code, invited_by, level, expires_at_str, used_by = invitation

            # Проверяем, не использовано ли приглашение
            if used_by:
                conn.close()
                await update.message.reply_text(
                    "❌ <b>Приглашение уже использовано</b>\n\n"
                    "Это приглашение уже было активировано.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="HTML",
                )
                return

            # Проверяем срок действия
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if datetime.datetime.now() > expires_at:
                conn.close()
                await update.message.reply_text(
                    "⏰ <b>Приглашение истекло</b>\n\n"
                    "Срок действия приглашения истёк.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="HTML",
                )
                return

            # Приглашение действительно - регистрируем пользователя
            self.bot_db.register_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                access_level=level,
            )

            # Отмечаем приглашение как использованное
            cursor.execute(
                """
                UPDATE user_invitations
                SET used_by = ?, used_at = ?
                WHERE invitation_code = ?
            """,
                (user.id, datetime.datetime.now().isoformat(), invitation_code),
            )

            conn.commit()
            conn.close()

            # Получаем информацию о пригласившем
            inviter_info = self.bot_db.get_user(invited_by)
            inviter_name = (
                inviter_info.get("username", "Администратор")
                if inviter_info
                else "Администратор"
            )

            menu = build_main_menu(level)

            level_names = {
                "user": "👤 User (Пользователь)",
                "operator": "⚙️ Operator (Оператор)",
                "engineer": "🔧 Engineer (Инженер)",
            }

            welcome_text = (
                f"🎉 <b>Добро пожаловать в КУБ-1063 Control Bot!</b>\n\n"
                f"👋 Привет, {user.first_name or user.username}!\n\n"
                f"✅ <b>Регистрация успешна</b>\n"
                f"🔐 <b>Уровень доступа:</b> {level_names.get(level, level)}\n"
                f"👤 <b>Приглашение от:</b> @{inviter_name}\n\n"
                f"<b>Ваши возможности:</b>\n"
                f"• Мониторинг датчиков КУБ-1063\n"
                f"• Просмотр текущих данных\n"
                f"• Управление системой (по уровню доступа)\n\n"
                "Выберите действие в меню ниже ⬇️"
            )

            await update.message.reply_text(
                welcome_text, reply_markup=menu, parse_mode="HTML"
            )

            self.bot_db.log_user_command(
                user.id, "start", f"invite_{invitation_code}", True
            )
            logger.info(
                f"✅ Новый пользователь {user.id} (@{user.username}) зарегистрирован по приглашению {invitation_code}"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка обработки приглашения: {e}")
            await update.message.reply_text(
                error_message(f"Ошибка обработки приглашения: {str(e)}"),
                parse_mode="HTML",
            )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - показать текущие данные"""
        user = update.effective_user

        # Проверяем права доступа
        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(
                error_message("У вас нет прав для чтения данных"), parse_mode="HTML"
            )
            return

        try:
            await send_typing_action(update, context)

            # Читаем данные из SQLite
            data = await self.get_current_data_from_db()

            if data:
                status_text = format_sensor_data(data)
                # Добавляем оценку причин аварии и нейтрализации
                assess = await self.compute_alarm_assessment(data)
                if assess["items"]:
                    status_text += "\n<b>🧯 Анализ аварии:</b>\n"
                    for it in assess["items"][:5]:
                        status_text += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
                    if assess["all_neutralized"] and data.get("alarm_relay") is True:
                        status_text += (
                            "\n✅ Причины устранены — можно сбросить реле аварии."
                        )
                # Подсказка: датчики восстановились, а аварии/реле ещё активны → предложить сброс
                recovery = await self.get_recent_sensor_recovery(minutes=15)
                relay_on = (
                    bool(data.get("alarm_relay")) if "alarm_relay" in data else False
                )
                alarms_cnt = int(data.get("active_alarms", 0) or 0)
                recovered_sensors = [
                    name.upper() for name, ok in recovery.items() if ok
                ]
                if recovered_sensors and (relay_on or alarms_cnt > 0):
                    rec_str = ", ".join(recovered_sensors)
                    status_text += (
                        f"\n\nℹ️ Обнаружено восстановление датчиков: {rec_str}.\n"
                        f"Можно выполнить сброс аварий (кнопка ниже)."
                    )
            else:
                status_text = error_message(
                    "Нет данных от КУБ-1063\n\n"
                    "Возможные причины:\n"
                    "• Основная система не запущена\n"
                    "• Нет связи с контроллером"
                )

            access_level = self.bot_db.get_user_access_level(user.id)
            badges = {}
            if data:
                badges = {
                    "alarms": int(data.get("active_alarms", 0) or 0),
                    "warnings": int(data.get("active_warnings", 0) or 0),
                }
            menu = build_main_menu(access_level, badges=badges)

            status_text = truncate_text(status_text, 4000)

            await update.message.reply_text(
                status_text, parse_mode="HTML", reply_markup=menu
            )

            self.bot_db.log_user_command(user.id, "read", None, True)

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message(f"Ошибка получения данных: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /reset — сброс аварий (для operator+)"""
        user = update.effective_user

        # Проверка прав и лимитов
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            await update.message.reply_text(
                error_message("У вас нет прав для сброса аварий"), parse_mode="HTML"
            )
            return
        allowed, rate_msg = check_command_rate_limit(user.id, self.bot_db)
        if not allowed:
            await update.message.reply_text(
                error_message(rate_msg), parse_mode="HTML"
            )
            return

        try:
            await update.message.reply_text(
                loading_message("Выполняется сброс аварий..."), parse_mode="HTML"
            )
            user_info = f"telegram_user_{user.id}_{user.username or user.first_name}"
            success, result = self.add_write_command_to_db(0x0020, 1, user_info)
            access_level = self.bot_db.get_user_access_level(user.id)
            data = await self.get_current_data_from_db() or {}
            badges = {
                "alarms": int((data or {}).get("active_alarms", 0) or 0),
                "warnings": int((data or {}).get("active_warnings", 0) or 0),
            }
            menu = build_main_menu(access_level, badges=badges)
            if success:
                await update.message.reply_text(
                    success_message(
                        f"Команда сброса отправлена. ID: <code>{result}</code>\nОжидайте 5–15 секунд."
                    ),
                    reply_markup=menu,
                    parse_mode="HTML",
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", True)
                # Плановая проверка результата через 12 сек
                try:
                    self.application.job_queue.run_once(
                        self._post_reset_check_job,
                        when=12,
                        data={"chat_id": update.effective_chat.id, "user_id": user.id},
                    )
                except Exception as jerr:
                    logger.warning(
                        f"⚠️ Не удалось запланировать проверку после сброса: {jerr}"
                    )
            else:
                await update.message.reply_text(
                    error_message(f"Не удалось отправить команду: {result}"),
                    reply_markup=menu,
                    parse_mode="HTML",
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", False)
        except Exception as e:
            logger.error(f"❌ Ошибка /reset: {e}")
            await update.message.reply_text(
                error_message(str(e)), parse_mode="HTML"
            )

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика системы"""
        user = update.effective_user

        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(
                error_message("У вас нет прав для чтения статистики"),
                parse_mode="HTML",
            )
            return

        try:
            await send_typing_action(update, context)

            # Простая статистика без UnifiedKUBSystem
            stats_text = "📈 <b>СТАТИСТИКА СИСТЕМЫ КУБ-1063</b>\n\n"

            # Получаем информацию из базы
            data = await self.get_current_data_from_db()
            if data:
                stats_text += f"🔄 <b>Последнее обновление:</b> <code>{data.get('updated_at', 'неизвестно')}</code>\n"
                stats_text += f"🌡️ <b>Текущая температура:</b> <code>{data.get('temp_inside', 0):.1f}°C</code>\n"
                stats_text += f"💧 <b>Влажность:</b> <code>{data.get('humidity', 0):.1f}%</code>\n"
                stats_text += (
                    f"🚨 <b>Активные аварии:</b> <code>{data.get('active_alarms', 0)}</code>\n"
                )
            else:
                stats_text += "❌ Нет данных от основной системы\n"

            # Получаем статистику пользователя
            user_stats = self.bot_db.get_user_stats(user.id)

            if user_stats:
                stats_text += "\n<b>👤 ВАША СТАТИСТИКА:</b>\n"
                stats_text += (
                    f"• Всего команд: <code>{user_stats.get('total_commands', 0)}</code>\n"
                )
                stats_text += f"• За сегодня: <code>{user_stats.get('commands_today', 0)}</code>\n"
                stats_text += (
                    f"• Успешность: <code>{user_stats.get('success_rate', 0):.1f}%</code>\n"
                )

            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)

            stats_text = truncate_text(stats_text, 4000)

            await update.message.reply_text(
                stats_text, parse_mode="HTML", reply_markup=menu
            )

            self.bot_db.log_user_command(user.id, "stats", None, True)

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            await update.message.reply_text(
                error_message(f"Ошибка получения статистики: {str(e)}"),
                parse_mode="HTML",
            )

    # =======================================================================
    # УПРАВЛЕНИЕ РОЛЯМИ ПОЛЬЗОВАТЕЛЕЙ
    # =======================================================================

    async def cmd_promote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /promote - повышение пользователя (только админы)"""
        user = update.effective_user

        # Логирование попытки изменения прав
        if SECURITY_AVAILABLE:
            log_security_event(
                "PRIVILEGE_ESCALATION_ATTEMPT",
                user_id=user.id,
                details={
                    "username": user.username,
                    "args": context.args,
                    "is_admin": user.id in self.config.telegram.admin_users,
                },
                level="WARNING"
                if user.id not in self.config.telegram.admin_users
                else "INFO",
            )

        # Проверяем права админа
        if user.id not in self.config.telegram.admin_users:
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        try:
            args = context.args
            if len(args) < 2:
                await update.message.reply_text(
                    "📖 Использование: <code>/promote @username уровень</code>\n\n"
                    "Доступные уровни:\n"
                    "• <code>user</code> - только чтение\n"
                    "• <code>operator</code> - чтение + сброс аварий\n"
                    "• <code>admin</code> - полный доступ\n"
                    "• <code>engineer</code> - максимальный доступ",
                    parse_mode="HTML",
                )
                return

            username = args[0].replace("@", "")
            new_level = args[1].lower()

            if new_level not in ["user", "operator", "admin", "engineer"]:
                await update.message.reply_text("❌ Неверный уровень доступа")
                return

            # Ищем пользователя по username
            target_user = self.bot_db.find_user_by_username(username)
            if not target_user:
                await update.message.reply_text(f"❌ Пользователь @{username} не найден")
                return

            # Обновляем уровень доступа
            success = self.bot_db.set_user_access_level(
                target_user["telegram_id"], new_level
            )

            if success:
                await update.message.reply_text(
                    f"✅ Пользователь @{username} повышен до уровня <code>{new_level}</code>",
                    parse_mode="HTML",
                )
                logger.info(f"🔝 Админ {user.id} повысил @{username} до {new_level}")
            else:
                await update.message.reply_text("❌ Ошибка обновления прав доступа")

        except Exception as e:
            logger.error(f"❌ Ошибка команды promote: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /users - список пользователей (только админы)"""
        user = update.effective_user

        if user.id not in self.config.telegram.admin_users:
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        try:
            users = self.bot_db.get_all_users()

            if not users:
                await update.message.reply_text("📋 Пользователи не найдены")
                return

            text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ:</b>\n\n"

            for user_data in users:
                username = user_data.get("username", "нет")
                first_name = user_data.get("first_name", "")
                access_level = user_data.get("access_level", "user")
                is_active = user_data.get("is_active", True)

                status = "✅" if is_active else "❌"

                text += f"{status} <b>{first_name}</b> (@{username})\n"
                text += f"   ID: <code>{user_data['telegram_id']}</code>\n"
                text += f"   Доступ: <code>{access_level}</code>\n\n"

            # Разбиваем длинное сообщение на части
            if len(text) > 4000:
                parts = [text[i : i + 4000] for i in range(0, len(text), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode="HTML")
            else:
                await update.message.reply_text(text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"❌ Ошибка команды users: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка"""
        user = update.effective_user

        await send_typing_action(update, context)

        access_level = self.bot_db.get_user_access_level(user.id)

        help_text = (
            "ℹ️ <b>Справка по КУБ-1063 Control Bot</b>\n\n"
            "<b>📱 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
            "• <code>/start</code> — главное меню\n"
            "• <code>/status</code> — показания датчиков\n"
            "• <code>/stats</code> — статистика системы\n"
            "• <code>/help</code> — эта справка\n\n"
        )

        if user.id in self.config.telegram.admin_users or access_level in [
            "admin",
            "engineer",
        ]:
            help_text += (
                "<b>👑 КОМАНДЫ АДМИНИСТРАТОРА:</b>\n"
                "• <code>/promote @user уровень</code> — изменить права\n"
                "• <code>/users</code> — список всех пользователей\n"
                "• <code>/switch_level <уровень></code> — временное переключение уровня\n"
                "• <code>/level_info</code> — информация о текущем уровне\n"
                "• <code>/block_user ID</code> — заблокировать пользователя\n"
                "• <code>/unblock_user ID</code> — разблокировать пользователя\n\n"
            )

        help_text += f"<b>🔐 ВАШ УРОВЕНЬ ДОСТУПА:</b> <code>{access_level}</code>\n"

        menu = build_main_menu(access_level)

        await update.message.reply_text(
            help_text, reply_markup=menu, parse_mode="HTML"
        )

    async def cmd_switch_level(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Команда /switch_level - временное переключение уровня доступа"""
        user = update.effective_user

        # Проверяем, что пользователь имеет высокий уровень доступа
        current_level = self.bot_db.get_user_access_level(user.id)
        if current_level not in ["admin", "engineer"]:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для переключения уровня доступа",
                parse_mode="HTML",
            )
            return

        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 <b>Использование:</b> <code>/switch_level <уровень> [часы]</code>\n\n"
                "<b>Доступные уровни:</b>\n"
                "• <code>user</code> — базовый уровень\n"
                "• <code>operator</code> — операторский уровень\n"
                "• <code>engineer</code> — инженерный уровень\n"
                "• <code>admin</code> — администраторский уровень\n\n"
                "<b>Примеры:</b>\n"
                "• <code>/switch_level user</code> — переключиться на user на 24 часа\n"
                "• <code>/switch_level operator 2</code> — переключиться на operator на 2 часа\n"
                "• <code>/switch_level restore</code> — восстановить оригинальный уровень",
                parse_mode="HTML",
            )
            return

        target_level = args[0].lower()
        duration_hours = int(args[1]) if len(args) > 1 else 24

        try:
            # Специальная команда для восстановления
            if target_level == "restore":
                success = self.bot_db.restore_user_original_level(user.id)
                if success:
                    new_level = self.bot_db.get_user_access_level(user.id)
                    await update.message.reply_text(
                        f"🔄 <b>Восстановлен оригинальный уровень доступа</b>\n\n"
                        f"Текущий уровень: <code>{new_level}</code>",
                        parse_mode="HTML",
                    )
                else:
                    await update.message.reply_text(
                        "❌ Ошибка восстановления уровня доступа"
                    )
                return

            # Проверяем валидность целевого уровня
            valid_levels = ["user", "operator", "engineer", "admin"]
            if target_level not in valid_levels:
                await update.message.reply_text(
                    f"❌ Неверный уровень: <code>{target_level}</code>\n"
                    f"Доступные: {', '.join(valid_levels)}",
                    parse_mode="HTML",
                )
                return

            # Устанавливаем временный уровень
            success = self.bot_db.set_user_temporary_level(
                user.id, target_level, duration_hours
            )
            if success:
                level_info = self.bot_db.get_user_level_info(user.id)
                await update.message.reply_text(
                    f"🕐 <b>Временный уровень доступа установлен</b>\n\n"
                    f"Новый уровень: <code>{target_level}</code>\n"
                    f"Длительность: {duration_hours} час(ов)\n"
                    f"Оригинальный уровень: <code>{level_info.get('original_level')}</code>\n\n"
                    f"Используйте <code>/switch_level restore</code> для восстановления.",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text("❌ Ошибка установки временного уровня")

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат времени. Укажите число часов."
            )
        except Exception as e:
            logger.error(f"❌ Ошибка переключения уровня: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_level_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /level_info - информация о текущем уровне доступа"""
        user = update.effective_user

        try:
            level_info = self.bot_db.get_user_level_info(user.id)
            if not level_info:
                await update.message.reply_text("❌ Пользователь не найден в системе")
                return

            current_level = level_info.get("current_level")
            original_level = level_info.get("original_level")
            is_temporary = level_info.get("is_temporary")
            temp_expires = level_info.get("temp_expires")

            info_text = "🔐 <b>Информация о вашем уровне доступа</b>\n\n"
            info_text += f"<b>Текущий уровень:</b> <code>{current_level}</code>\n"

            if is_temporary and original_level:
                info_text += f"<b>Оригинальный уровень:</b> <code>{original_level}</code>\n"
                info_text += "<b>Статус:</b> Временный\n"
                if temp_expires:
                    info_text += f"<b>Истекает:</b> {temp_expires}\n"
                info_text += (
                    "\n💡 Используйте <code>/switch_level restore</code> для восстановления."
                )
            else:
                info_text += "<b>Статус:</b> Постоянный\n"

            # Показываем текущие права
            permissions = self.bot_db.get_access_permissions(current_level)
            if permissions:
                info_text += "\n<b>🔓 Ваши права:</b>\n"
                if permissions.get("can_read"):
                    info_text += "• ✅ Чтение данных\n"
                if permissions.get("can_write"):
                    info_text += "• ✅ Запись команд\n"
                if permissions.get("can_reset_alarms"):
                    info_text += "• ✅ Сброс аварий\n"

            await update.message.reply_text(info_text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об уровне: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_block_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /block_user - блокировка пользователя"""
        user = update.effective_user

        # Логирование попытки блокировки пользователя
        if SECURITY_AVAILABLE:
            log_security_event(
                "USER_BLOCK_ATTEMPT",
                user_id=user.id,
                details={"username": user.username, "args": context.args},
                level="WARNING",
            )

        # Проверяем права доступа
        access_level = self.bot_db.get_user_access_level(user.id)
        if access_level not in ["engineer", "admin"]:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для блокировки пользователей",
                parse_mode="HTML",
            )
            return

        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 <b>Использование:</b> <code>/block_user ID_пользователя</code>\n\n"
                "<b>Пример:</b> <code>/block_user 123456789</code>\n\n"
                "Используйте команду <code>/users</code> для получения списка пользователей с их ID.",
                parse_mode="HTML",
            )
            return

        try:
            target_user_id = int(args[0])

            # Проверяем, что пользователь не блокирует самого себя
            if target_user_id == user.id:
                await update.message.reply_text(
                    "❌ Вы не можете заблокировать самого себя"
                )
                return

            # Блокируем пользователя
            success = self.bot_db.deactivate_user(target_user_id)

            if success:
                # Получаем информацию о заблокированном пользователе
                target_user = self.bot_db.get_user(target_user_id)
                target_username = (
                    target_user.get("username", "Unknown") if target_user else "Unknown"
                )

                await update.message.reply_text(
                    f"🔒 <b>Пользователь заблокирован</b>\n\n"
                    f"👤 <b>Пользователь:</b> @{target_username} (ID: {target_user_id})\n"
                    f"👮‍♂️ <b>Заблокировал:</b> @{user.username or 'Unknown'}\n\n"
                    f"Пользователь больше не сможет использовать бота до разблокировки.",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка блокировки пользователя. Возможно, пользователь не найден."
                )

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат ID пользователя. Укажите числовой ID."
            )
        except Exception as e:
            logger.error(f"❌ Ошибка блокировки пользователя: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_unblock_user(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Команда /unblock_user - разблокировка пользователя"""
        user = update.effective_user

        # Проверяем права доступа
        access_level = self.bot_db.get_user_access_level(user.id)
        if access_level not in ["engineer", "admin"]:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для разблокировки пользователей",
                parse_mode="HTML",
            )
            return

        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 <b>Использование:</b> <code>/unblock_user ID_пользователя</code>\n\n"
                "<b>Пример:</b> <code>/unblock_user 123456789</code>\n\n"
                "Используйте меню <b>Настройки → Управление пользователями → Разблокировать пользователя</b> "
                "для получения списка заблокированных пользователей.",
                parse_mode="HTML",
            )
            return

        try:
            target_user_id = int(args[0])

            # Разблокируем пользователя (устанавливаем is_active = 1)
            try:
                from core.config_manager import get_config
                with sqlite3.connect(get_config().database.commands_db) as conn:
                    cursor = conn.execute(
                        """
                        UPDATE telegram_users
                        SET is_active = 1, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """,
                        (target_user_id,),
                    )

                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при разблокировке: {db_error}")
                success = False

            if success:
                # Получаем информацию о разблокированном пользователе
                target_user = self.bot_db.get_user(target_user_id)
                target_username = (
                    target_user.get("username", "Unknown") if target_user else "Unknown"
                )

                await update.message.reply_text(
                    f"✅ <b>Пользователь разблокирован</b>\n\n"
                    f"👤 <b>Пользователь:</b> @{target_username} (ID: {target_user_id})\n"
                    f"👮‍♂️ <b>Разблокировал:</b> @{user.username or 'Unknown'}\n\n"
                    f"Пользователь снова может использовать бота.",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка разблокировки пользователя. Возможно, пользователь не найден или уже активен."
                )

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат ID пользователя. Укажите числовой ID."
            )
        except Exception as e:
            logger.error(f"❌ Ошибка разблокировки пользователя: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    # =======================================================================
    # ОБРАБОТЧИКИ CALLBACK QUERY (INLINE КНОПКИ)
    # =======================================================================

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()

        data = query.data

        try:
            await send_typing_action(query, context)

            if data == "show_status":
                await self._handle_show_status(query, context)
            elif data == "show_extended":
                await self._handle_show_extended(query, context)
            elif data == "refresh_status":
                await self._handle_refresh_status(query, context)
            elif data == "show_stats":
                await self._handle_show_stats(query, context)
            elif data == "refresh_stats":
                await self._handle_refresh_stats(query, context)
            elif data == "reset_alarms":
                await self._handle_reset_alarms(query, context)
            elif data == "reset_alarms_confirmed":
                await self._handle_confirm_reset_alarms(query, context)
            elif data == "ack_alarms":
                await self._handle_ack_alarms(query, context)
            elif data == "main_menu":
                await self._handle_main_menu(query, context)
            elif data == "show_help":
                await self._handle_show_help(query, context)
            elif data == "settings":
                await self._handle_settings(query, context)

            # НОВЫЕ ОБРАБОТЧИКИ МЕНЮ НАСТРОЕК
            elif data == "manage_users":
                await self._handle_manage_users(query, context)
            elif data == "switch_level_menu":
                await self._handle_switch_level_menu(query, context)
            elif data == "system_config":
                await self._handle_system_config(query, context)
            elif data == "system_logs":
                await self._handle_system_logs(query, context)
            elif data == "permissions_config":
                await self._handle_permissions_config(query, context)
            elif data == "backup_config":
                await self._handle_backup_config(query, context)

            # УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
            elif data == "list_users":
                await self._handle_list_users(query, context)
            elif data == "invite_user":
                await self._handle_invite_user(query, context)
            elif data == "block_user":
                await self._handle_block_user(query, context)
            elif data == "unblock_user":
                await self._handle_unblock_user(query, context)
            elif data == "change_permissions":
                await self._handle_change_permissions(query, context)
            elif data == "user_stats":
                await self._handle_user_stats(query, context)

            # ПЕРЕКЛЮЧЕНИЕ УРОВНЕЙ
            elif data.startswith("temp_level_"):
                level = data.replace("temp_level_", "")
                await self._handle_temp_level(query, context, level)
            elif data == "restore_level":
                await self._handle_restore_level(query, context)
            elif data == "level_info_menu":
                await self._handle_level_info_menu(query, context)

            # ИНТЕРАКТИВНОЕ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
            elif data.startswith("promote_user_"):
                user_id = int(data.replace("promote_user_", ""))
                await self._handle_promote_user_selected(query, context, user_id)
            elif data.startswith("block_user_"):
                user_id = int(data.replace("block_user_", ""))
                await self._handle_block_user_selected(query, context, user_id)
            elif data.startswith("unblock_user_"):
                user_id = int(data.replace("unblock_user_", ""))
                await self._handle_unblock_user_selected(query, context, user_id)
            elif data.startswith("set_level_"):
                parts = data.replace("set_level_", "").split("_")
                user_id = int(parts[0])
                new_level = parts[1]
                await self._handle_set_user_level(query, context, user_id, new_level)
            elif data.startswith("invite_level_"):
                level = data.replace("invite_level_", "")
                await self._handle_invite_level_selected(query, context, level)
            elif data.startswith("confirm_invite_"):
                level = data.replace("confirm_invite_", "")
                await self._handle_confirm_invite(query, context, level)
            elif data.startswith("copy_link_"):
                await query.answer(
                    "📋 Ссылка готова к копированию! Нажмите на неё выше ☝️",
                    show_alert=True,
                )
            elif data == "promote_users":
                await self._handle_change_permissions(query, context)

            else:
                await query.edit_message_text(
                    error_message("Неизвестная команда"), parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback {data}: {e}")
            access_level = self.bot_db.get_user_access_level(query.from_user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка выполнения команды: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )

    async def _handle_main_menu(self, query, context):
        """Показать главное меню"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)

        await query.edit_message_text(
            "🏠 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=menu,
            parse_mode="HTML",
        )

    async def _handle_show_status(self, query, context):
        """Показать статус"""
        await self._handle_refresh_status(query, context)

    async def _handle_show_extended(self, query, context):
        """Показать расширенные данные"""
        user = query.from_user
        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для чтения данных"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        try:
            # Читаем данные из SQLite
            data = await self.get_current_data_from_db()
            
            if data:
                status_text = format_extended_sensor_data(data)
            else:
                status_text = error_message(
                    "Нет данных от КУБ-1063\n\n"
                    "Возможные причины:\n"
                    "• Основная система не запущена\n"
                    "• Нет связи с контроллером"
                )

            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            status_text = truncate_text(status_text, 4000)

            await query.edit_message_text(
                status_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка показа расширенных данных: {e}")
            await query.edit_message_text(
                error_message("Ошибка получения расширенных данных"),
                parse_mode="HTML",
            )

    async def _handle_refresh_status(self, query, context):
        """Обновление статуса из SQLite базы"""
        user = query.from_user

        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для чтения данных"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        try:
            # Читаем данные из SQLite
            data = await self.get_current_data_from_db()

            if data:
                # Оптимистичный режим: если после сброса прошло <35с, считаем реле ВЫКЛ
                try:
                    import time as _t

                    deadline = self._optimistic_clear_until.get(query.message.chat_id)
                    if deadline and _t.time() < deadline:
                        data["alarm_relay"] = False
                except Exception:
                    pass
                status_text = format_sensor_data(data)
                assess = await self.compute_alarm_assessment(data)
                if assess["items"]:
                    status_text += "\n<b>🧯 Анализ аварии:</b>\n"
                    for it in assess["items"][:5]:
                        status_text += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
                    if assess["all_neutralized"] and data.get("alarm_relay") is True:
                        status_text += (
                            "\n✅ Причины устранены — можно сбросить реле аварии."
                        )
            else:
                status_text = error_message(
                    "Нет данных от КУБ-1063\n\n"
                    "Возможные причины:\n"
                    "• Основная система не запущена\n"
                    "• Нет связи с контроллером"
                )

            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)

            status_text = truncate_text(status_text, 4000)

            # Проверяем, изменился ли контент перед редактированием
            try:
                await query.edit_message_text(
                    status_text, reply_markup=menu, parse_mode="HTML"
                )
                # Запоминаем master‑message id для чата (обновили существующее)
                try:
                    self.bot_db.set_last_message_id(
                        query.message.chat_id, query.message.message_id
                    )
                except Exception:
                    pass
            except Exception as edit_error:
                if "message is not modified" in str(edit_error).lower():
                    # Сообщение не изменилось, просто отправляем ответ без редактирования
                    await query.answer("🔄 Данные обновлены", show_alert=False)
                else:
                    raise edit_error

            self.bot_db.log_user_command(user.id, "read", None, data is not None)

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка получения данных: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )

    async def _handle_show_stats(self, query, context):
        """Показать статистику"""
        await self._handle_refresh_stats(query, context)

    async def _handle_refresh_stats(self, query, context):
        """Обновление статистики"""
        user = query.from_user

        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для чтения статистики"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        try:
            # Простая статистика
            stats_text = "📈 <b>СТАТИСТИКА СИСТЕМЫ КУБ-1063</b>\n\n"

            data = await self.get_current_data_from_db()
            if data:
                stats_text += f"🔄 <b>Последнее обновление:</b> <code>{data.get('updated_at', 'неизвестно')}</code>\n"
                stats_text += (
                    f"🌡️ <b>Температура:</b> <code>{data.get('temp_inside', 0):.1f}°C</code>\n"
                )
                stats_text += f"💧 <b>Влажность:</b> <code>{data.get('humidity', 0):.1f}%</code>\n"
            else:
                stats_text += "❌ Нет данных от основной системы\n"

            user_stats = self.bot_db.get_user_stats(user.id)
            if user_stats:
                stats_text += "\n<b>👤 ВАША СТАТИСТИКА:</b>\n"
                stats_text += (
                    f"• Всего команд: <code>{user_stats.get('total_commands', 0)}</code>\n"
                )

            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)

            stats_text = truncate_text(stats_text, 4000)

            # Проверяем, изменился ли контент перед редактированием
            try:
                await query.edit_message_text(
                    stats_text, reply_markup=menu, parse_mode="HTML"
                )
            except Exception as edit_error:
                if "message is not modified" in str(edit_error).lower():
                    # Сообщение не изменилось, просто отправляем ответ без редактирования
                    await query.answer("📈 Статистика обновлена", show_alert=False)
                else:
                    raise edit_error

            self.bot_db.log_user_command(user.id, "stats", None, True)

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка получения статистики: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )

    async def _handle_reset_alarms(self, query, context):
        """Запрос подтверждения сброса аварий"""
        user = query.from_user

        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для сброса аварий"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        confirmation_menu = build_confirmation_menu(
            "reset_alarms_confirmed", "main_menu"
        )

        await query.edit_message_text(
            warning_message(
                "Вы уверены, что хотите сбросить все аварии?\n\nЭто действие нельзя отменить!"
            ),
            reply_markup=confirmation_menu,
            parse_mode="HTML",
        )

    async def _handle_confirm_reset_alarms(self, query, context):
        """Подтвержденный сброс аварий через систему команд"""
        user = query.from_user

        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для сброса аварий"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        try:
            # Показываем процесс выполнения
            await query.edit_message_text(
                loading_message("Выполняется сброс аварий..."), parse_mode="HTML"
            )

            # Добавляем команду сброса в очередь (регистр 0x0020, значение 1)
            user_info = f"telegram_user_{user.id}_{user.username or user.first_name}"
            success, result = self.add_write_command_to_db(0x0020, 1, user_info)

            access_level = self.bot_db.get_user_access_level(user.id)
            data = await self.get_current_data_from_db() or {}
            badges = {
                "alarms": int((data or {}).get("active_alarms", 0) or 0),
                "warnings": int((data or {}).get("active_warnings", 0) or 0),
            }
            menu = build_main_menu(access_level, badges=badges)

            if success:
                logger.info(
                    "[RESET] Команда сброса добавлена в очередь успешно (id=%s)", result
                )
                await query.edit_message_text(
                    success_message(
                        f"🔄 Команда сброса аварий отправлена!\n\nID команды: <code>{result}</code>\n\nВыполнение может занять несколько секунд."
                    ),
                    reply_markup=menu,
                    parse_mode="HTML",
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", True)
                # Включаем оптимистичный режим (до 35 сек реле считаем ВЫКЛ)
                try:
                    chat_id = query.message.chat_id
                    import time as _t

                    self._optimistic_clear_until[chat_id] = _t.time() + 35
                    logger.info(
                        "[RESET] Включен оптимистичный режим для chat_id=%s до %s",
                        chat_id,
                        int(self._optimistic_clear_until[chat_id]),
                    )
                    # Перерисуем мастер‑сообщение, если знаем его id
                    state = self.bot_db.get_bot_state(chat_id)
                    mid = state.get("last_message_id")
                    if mid:
                        data2 = await self.get_current_data_from_db() or {}
                        data2["alarm_relay"] = False
                        status_text2 = format_sensor_data(data2)
                        assess2 = await self.compute_alarm_assessment(data2)
                        if assess2["items"]:
                            status_text2 += "\n<b>🧯 Анализ аварии:</b>\n"
                            for it in assess2["items"][:5]:
                                status_text2 += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
                            if assess2["all_neutralized"]:
                                status_text2 += "\n✅ Причины устранены — можно сбросить реле аварии."
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=mid,
                            text=truncate_text(status_text2, 4000),
                            parse_mode="HTML",
                        )
                        logger.info(
                            "[RESET] Мастер‑сообщение обновлено в оптимистичном режиме (chat_id=%s, mid=%s)",
                            chat_id,
                            mid,
                        )
                except Exception as _e:
                    logger.warning(
                        f"⚠️ Не удалось перерисовать статус (оптимистично): {_e}"
                    )
                # Плановая проверка результата через 12 сек
                try:
                    self.application.job_queue.run_once(
                        self._post_reset_check_job,
                        when=12,
                        data={"chat_id": query.message.chat_id, "user_id": user.id},
                    )
                except Exception as jerr:
                    logger.warning(
                        f"⚠️ Не удалось запланировать проверку после сброса: {jerr}"
                    )
            else:
                await query.edit_message_text(
                    error_message(f"Ошибка отправки команды:\n{result}"),
                    reply_markup=menu,
                    parse_mode="HTML",
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", False)

        except Exception as e:
            logger.error(f"❌ Ошибка сброса аварий: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )

    async def _alarm_watch_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Фоновая задача: оповещение об авариях"""
        try:
            data = await self.get_current_data_from_db()
            if not data:
                return
            alarms = int(data.get("active_alarms", 0) or 0)
            warns = int(data.get("active_warnings", 0) or 0)
            now = int(time.time())
            # Условия уведомления: появление/рост аварий или периодическое напоминание раз в 15 минут
            changed = alarms > 0 and (alarms != self._last_alarm_count)
            periodic = alarms > 0 and (now - self._last_alarm_notify_ts >= 15 * 60)
            cleared = self._last_alarm_count > 0 and alarms == 0
            logger.debug(
                "[ALARM_WATCH] alarms=%s warns=%s changed=%s periodic=%s cleared=%s",
                alarms,
                warns,
                changed,
                periodic,
                cleared,
            )

            if changed or periodic:
                # Кому отправлять: админам и операторам
                recipients = set(self.config.telegram.admin_users or [])
                try:
                    users = self.bot_db.get_all_users()
                    for u in users:
                        lvl = u.get("access_level") or "user"
                        if u.get("is_active", 1) and lvl in (
                            "operator",
                            "engineer",
                            "admin",
                        ):
                            recipients.add(int(u.get("telegram_id")))
                except Exception:
                    pass
                if recipients:
                    # Подготовим мастер‑сообщение (редактируемое)
                    try:
                        status_text = format_sensor_data(data)
                        assess = await self.compute_alarm_assessment(data)
                        if assess["items"]:
                            status_text += "\n<b>🧯 Анализ аварии:</b>\n"
                            for it in assess["items"][:5]:
                                status_text += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
                    except Exception as _e:
                        logger.warning(f"⚠️ Ошибка подготовки текста аварии: {_e}")
                        status_text = (
                            f"🚨 Обнаружены активные аварии: {alarms}\n"
                            f"⚠️ Предупреждения: {warns}"
                        )
                    for uid in recipients:
                        try:
                            # Пытаемся отредактировать мастер‑сообщение, чтобы не плодить новые
                            state = self.bot_db.get_bot_state(uid)
                            mid = state.get("last_message_id")
                            if mid:
                                access_level = self.bot_db.get_user_access_level(uid)
                                menu = build_main_menu(access_level)
                                await context.bot.edit_message_text(
                                    chat_id=uid,
                                    message_id=mid,
                                    text=truncate_text(status_text, 4000),
                                    reply_markup=menu,
                                    parse_mode="HTML",
                                )
                            else:
                                # Создадим первое мастер‑сообщение для чата
                                sent = await context.bot.send_message(
                                    chat_id=uid,
                                    text=truncate_text(status_text, 4000),
                                    parse_mode="HTML",
                                )
                                self.bot_db.set_last_message_id(uid, sent.message_id)
                            # Звуковой пинг только при появлении аварий (если не включен тихий режим)
                            try:
                                if not self.bot_db.is_ack_active(uid):
                                    await self._send_sound_ping(
                                        context, uid, f"🚨 Аварии: {alarms}"
                                    )
                            except Exception:
                                pass
                        except Exception as send_err:
                            logger.warning(
                                f"⚠️ Не удалось обновить мастер‑сообщение {uid}: {send_err}"
                            )
                    self._last_alarm_notify_ts = now
            elif cleared:
                # Сообщаем об устранении — обновляя мастер‑сообщение, не создавая новые
                recipients = set(self.config.telegram.admin_users or [])
                try:
                    users = self.bot_db.get_all_users()
                    for u in users:
                        lvl = u.get("access_level") or "user"
                        if u.get("is_active", 1) and lvl in (
                            "operator",
                            "engineer",
                            "admin",
                        ):
                            recipients.add(int(u.get("telegram_id")))
                except Exception:
                    pass
                status_text = format_sensor_data(data)
                assess = await self.compute_alarm_assessment(data)
                if assess["items"]:
                    status_text += "\n<b>🧯 Анализ аварии:</b>\n"
                    for it in assess["items"][:5]:
                        status_text += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
                status_text += "\n✅ Аварии устранены"
                for uid in recipients:
                    try:
                        state = self.bot_db.get_bot_state(uid)
                        mid = state.get("last_message_id")
                        access_level = self.bot_db.get_user_access_level(uid)
                        menu = build_main_menu(access_level)
                        if mid:
                            await context.bot.edit_message_text(
                                chat_id=uid,
                                message_id=mid,
                                text=truncate_text(status_text, 4000),
                                reply_markup=menu,
                                parse_mode="HTML",
                            )
                            logger.debug(
                                "[ALARM_WATCH] Обновлено мастер‑сообщение (uid=%s, mid=%s)",
                                uid,
                                mid,
                            )
                        else:
                            sent = await context.bot.send_message(
                                chat_id=uid,
                                text=truncate_text(status_text, 4000),
                                parse_mode="HTML",
                            )
                            self.bot_db.set_last_message_id(uid, sent.message_id)
                        # Без отдельного сообщения: всё отрисовано в мастер‑сообщении
                    except Exception as send_err:
                        logger.warning(
                            f"⚠️ Не удалось обновить мастер‑сообщение {uid}: {send_err}"
                        )
            else:
                # Нет изменений, но проверим восстановление датчиков и активное реле/аварии
                recovery = await self.get_recent_sensor_recovery(minutes=15)
                recovered = [k.upper() for k, v in recovery.items() if v]
                if (
                    recovered
                    and (active_alarms_val := data.get("active_alarms")) is not None
                ):
                    relay_on = (
                        bool(data.get("alarm_relay"))
                        if "alarm_relay" in data
                        else False
                    )
                    alarms_cnt = int(active_alarms_val or 0)
                    if relay_on or alarms_cnt > 0:
                        recipients = set(self.config.telegram.admin_users or [])
                        try:
                            users = self.bot_db.get_all_users()
                            for u in users:
                                lvl = u.get("access_level") or "user"
                                if u.get("is_active", 1) and lvl in (
                                    "operator",
                                    "engineer",
                                    "admin",
                                ):
                                    recipients.add(int(u.get("telegram_id")))
                        except Exception:
                            pass
                        if recipients:
                            text = (
                                f"ℹ️ Датчики восстановились: {', '.join(recovered)};"
                                f" аварии/реле ещё активны. Рекомендуем выполнить сброс из меню."
                            )
                            # Обновляем мастер‑сообщение краткой подсказкой
                            for uid in recipients:
                                try:
                                    state = self.bot_db.get_bot_state(uid)
                                    mid = state.get("last_message_id")
                                    access_level = self.bot_db.get_user_access_level(
                                        uid
                                    )
                                    menu = build_main_menu(access_level)
                                    if mid:
                                        await context.bot.edit_message_text(
                                            chat_id=uid,
                                            message_id=mid,
                                            text=truncate_text(text, 4000),
                                            reply_markup=menu,
                                            parse_mode="HTML",
                                        )
                                    else:
                                        sent = await context.bot.send_message(
                                            chat_id=uid,
                                            text=truncate_text(text, 4000),
                                            parse_mode="HTML",
                                        )
                                        self.bot_db.set_last_message_id(
                                            uid, sent.message_id
                                        )
                                    # Подсказку даём только в мастер‑сообщении, без отдельного пинга
                                except Exception as send_err:
                                    logger.warning(
                                        f"⚠️ Не удалось обновить мастер‑сообщение {uid}: {send_err}"
                                    )

            self._last_alarm_count = alarms
            self._last_warning_count = warns
        except Exception as e:
            logger.warning(f"⚠️ Ошибка фонового мониторинга аварий: {e}")

    async def _post_reset_check_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверить, снялись ли аварии после сброса, и уведомить пользователя"""
        try:
            data = await self.get_current_data_from_db() or {}
            alarms = int(data.get("active_alarms", 0) or 0)
            relay_on = bool(data.get("alarm_relay")) if "alarm_relay" in data else False
            chat_id = (context.job.data or {}).get("chat_id")
            if not chat_id:
                return
            # Подготовим текущее представление статуса для мастер‑сообщения
            # Оптимистичное окно: если активно — считаем реле ВЫКЛ для рендера
            try:
                import time as _t

                deadline = self._optimistic_clear_until.get(chat_id)
                optimistic = bool(deadline and _t.time() < deadline)
            except Exception:
                optimistic = False
            data_for_render = dict(data)
            if optimistic:
                data_for_render["alarm_relay"] = False

            status_text = format_sensor_data(data_for_render)
            assess = await self.compute_alarm_assessment(data_for_render)
            if assess["items"]:
                status_text += "\n<b>🧯 Анализ аварии:</b>\n"
                for it in assess["items"][:5]:
                    status_text += f"• {it['title']} — {'УСТРАНЕНА' if it['neutralized'] else 'АКТИВНА'}\n"
            # Итоговая подпись об успехе/остатке
            if optimistic or (alarms == 0 and not relay_on):
                status_text += "\n✅ Аварии сняты"
            else:
                if alarms > 0 or relay_on:
                    tail = []
                    if alarms > 0:
                        tail.append(f"Аварии: {alarms}")
                    if relay_on:
                        tail.append("реле аварии ВКЛ")
                    status_text += "\n❗ " + ", ".join(tail)

            # Обновляем мастер‑сообщение вместо отправки нового
            try:
                state = self.bot_db.get_bot_state(chat_id)
                mid = state.get("last_message_id")
                access_level = self.bot_db.get_user_access_level(chat_id)
                menu = build_main_menu(access_level)
                if mid:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=mid,
                        text=truncate_text(status_text, 4000),
                        reply_markup=menu,
                        parse_mode="HTML",
                    )
                else:
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=truncate_text(status_text, 4000),
                        parse_mode="HTML",
                    )
                    self.bot_db.set_last_message_id(chat_id, sent.message_id)
            except Exception as e_edit:
                logger.warning(
                    f"⚠️ Не удалось обновить мастер‑сообщение в пост‑проверке: {e_edit}"
                )
            # Пинга здесь не шлём — избегаем лишних сообщений в ленте
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки после сброса: {e}")

    async def _handle_ack_alarms(self, query, context):
        """Включить тихий режим (ACK) для текущего чата на 45 минут"""
        try:
            chat_id = query.message.chat_id
            self.bot_db.set_ack_until(chat_id, minutes=45)
            await query.answer("🤫 Тихий режим включён на 45 минут", show_alert=True)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка установки тихого режима: {e}")
            await query.answer("❌ Не удалось включить тихий режим", show_alert=True)

    async def _delete_message_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет вспомогательное пинг‑сообщение"""
        try:
            data = context.job.data or {}
            await context.bot.delete_message(
                chat_id=data["chat_id"], message_id=data["message_id"]
            )
        except Exception as e:
            logger.debug(f"[PING] Не удалось удалить пинг‑сообщение: {e}")

    async def _send_sound_ping(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        text: str,
        delete_after: Optional[int] = None,
    ):
        """Отправляет короткий звуковой пинг и по таймеру удаляет его, чтобы не захламлять ленту."""
        try:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=text, disable_notification=False
            )
            da = (
                delete_after
                if delete_after is not None
                else self._sound_ping_delete_after
            )
            if (
                hasattr(self, "application")
                and self.application
                and self.application.job_queue
                and da > 0
            ):
                self.application.job_queue.run_once(
                    self._delete_message_job,
                    when=da,
                    data={"chat_id": chat_id, "message_id": sent.message_id},
                )
        except Exception as e:
            logger.debug(f"[PING] Ошибка отправки звукового пинга: {e}")

    def get_recent_write_commands(self, limit: int = 5):
        """Последние команды записи из очереди"""
        try:
            from core.config_manager import get_config
            with sqlite3.connect(get_config().database.commands_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT id, register, value, status, created_at, executed_at, error_message
                    FROM write_commands
                    ORDER BY datetime(created_at) DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка чтения очереди команд: {e}")
            return []

    async def cmd_alarms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /alarms — сводка по авариям/предупреждениям"""
        user = update.effective_user
        try:
            data = await self.get_current_data_from_db() or {}
            alarms = int(data.get("active_alarms", 0) or 0)
            warns = int(data.get("active_warnings", 0) or 0)
            updated = data.get("updated_at") or "—"
            txt = f"🧭 Сводка аварий\n\n🚨 Аварии: {alarms}\n⚠️ Предупреждения: {warns}\n⏱ Обновлено: {updated}"
            # Детализация известных аварий по битам
            if isinstance(data.get("active_alarms"), int) and data.get("active_alarms"):
                details = decode_active_alarms(int(data["active_alarms"]), max_items=12)
                if details:
                    txt += "\n\nИзвестные аварии:\n" + "\n".join(
                        f"• {d}" for d in details
                    )
            if alarms > 0:
                txt += "\n\nДля сброса используйте кнопку в меню или команду /reset (operator+)."
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(
                access_level, badges={"alarms": alarms, "warnings": warns}
            )
            await update.message.reply_text(txt, reply_markup=menu)
            self.bot_db.log_user_command(user.id, "alarms", None, True)
        except Exception as e:
            logger.error(f"❌ Ошибка /alarms: {e}")
            await update.message.reply_text(
                error_message(str(e)), parse_mode="HTML"
            )

    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /queue — последние команды записи"""
        user = update.effective_user
        try:
            cmds = self.get_recent_write_commands(limit=5)
            if not cmds:
                await update.message.reply_text("📭 Очередь команд пуста")
                return
            lines = ["📝 Последние команды записи:"]
            for c in cmds:
                cid = str(c.get("id"))[:8]
                reg = int(c.get("register", 0) or 0)
                val = c.get("value")
                st = c.get("status")
                created = c.get("created_at") or ""
                icon = (
                    "✅"
                    if st == "completed"
                    else ("⏳" if st in ("pending", "executing") else "❌")
                )
                lines.append(f"{icon} {cid} — 0x{reg:04X}={val} [{st}] ({created})")
            await update.message.reply_text("\n".join(lines))
            self.bot_db.log_user_command(user.id, "queue", None, True)
        except Exception as e:
            logger.error(f"❌ Ошибка /queue: {e}")
            await update.message.reply_text(
                error_message(str(e)), parse_mode="HTML"
            )

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /whoami — информация о пользователе и доступах"""
        user = update.effective_user
        try:
            info = self.bot_db.get_user_level_info(user.id) or {}
            level = info.get("current_level", "user")
            perms = self.bot_db.get_access_permissions(level) or {}
            allowed, msg = check_command_rate_limit(user.id, self.bot_db)
            txt = [
                "👤 Ваш профиль",
                f"ID: <code>{user.id}</code>",
                f"Уровень: <code>{level}</code>"
                + (" (временный)" if info.get("is_temporary") else ""),
            ]
            if info.get("temp_expires"):
                txt.append(f"Истекает: {info.get('temp_expires')}")
            txt.append("\nПрава:")
            if perms.get("can_read"):
                txt.append("• ✅ Чтение")
            if perms.get("can_write"):
                txt.append("• ✅ Запись")
            if perms.get("can_reset_alarms"):
                txt.append("• ✅ Сброс аварий")
            txt.append(f"\nЛимит команд: {msg}")
            await update.message.reply_text("\n".join(txt), parse_mode="HTML")
            self.bot_db.log_user_command(user.id, "whoami", None, True)
        except Exception as e:
            logger.error(f"❌ Ошибка /whoami: {e}")
            await update.message.reply_text(
                error_message(str(e)), parse_mode="HTML"
            )

    async def _handle_show_help(self, query, context):
        """Показать справку через callback"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        help_text = (
            "ℹ️ <b>Справка по КУБ-1063 Control Bot</b>\n\n"
            "<b>🔘 КНОПКИ МЕНЮ:</b>\n"
            "• 📊 Показания — текущие данные с датчиков\n"
            "• 🔄 Обновить — получить свежие данные\n"
            "• 📈 Статистика — статистика системы\n"
            "• 🏠 Главное меню — возврат в главное меню\n"
        )

        if access_level in ("operator", "admin", "engineer"):
            help_text += "• 🚨 Сброс аварий — сброс активных аварий\n"

        if access_level in ("admin", "engineer"):
            help_text += "• ⚙️ Настройки — управление системой\n"

        help_text += f"\n<b>🔐 ВАШ ДОСТУП:</b> <code>{access_level}</code>\n"
        help_text += "\n💡 <b>Совет:</b> Кнопки быстрее команд!"

        menu = build_main_menu(access_level)

        await query.edit_message_text(
            help_text, reply_markup=menu, parse_mode="HTML"
        )

    async def _handle_settings(self, query, context):
        """Настройки системы"""
        user = query.from_user

        # Проверяем базовые права доступа
        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для настроек"),
                reply_markup=back_menu,
                parse_mode="HTML",
            )
            return

        access_level = self.bot_db.get_user_access_level(user.id)

        # Получаем информацию о пользователе для отображения
        user_info = self.bot_db.get_user(user.id)
        username = user_info.get("username", "Unknown") if user_info else "Unknown"

        settings_text = (
            f"⚙️ <b>НАСТРОЙКИ СИСТЕМЫ</b>\n\n"
            f"👤 <b>Пользователь:</b> @{username}\n"
            f"🔐 <b>Уровень доступа:</b> <code>{access_level}</code>\n\n"
            f"Выберите раздел настроек:"
        )

        from apps.edge.telegram_bot.bot_utils import build_settings_menu

        menu = build_settings_menu(access_level)

        try:
            await query.edit_message_text(
                settings_text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("⚙️ Меню настроек открыто", show_alert=False)
            else:
                raise edit_error

    # =======================================================================
    # НОВЫЕ ОБРАБОТЧИКИ МЕНЮ НАСТРОЕК
    # =======================================================================

    async def _handle_manage_users(self, query, context):
        """Управление пользователями"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для управления пользователями", show_alert=True
            )
            return

        users_text = (
            f"👥 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>\n\n"
            f"🔐 <b>Ваш уровень:</b> <code>{access_level}</code>\n\n"
            f"Выберите действие:"
        )

        from apps.edge.telegram_bot.bot_utils import build_user_management_menu

        menu = build_user_management_menu(access_level)

        try:
            await query.edit_message_text(
                users_text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("👥 Управление пользователями", show_alert=False)
            else:
                raise edit_error

    async def _handle_switch_level_menu(self, query, context):
        """Меню переключения уровня доступа"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для переключения уровня", show_alert=True
            )
            return

        # Упрощенный текст без проверки временных уровней (методы еще не загружены)
        switch_text = (
            f"🔄 <b>ПЕРЕКЛЮЧЕНИЕ УРОВНЯ ДОСТУПА</b>\n\n"
            f"📊 <b>Текущий уровень:</b> <code>{access_level}</code>\n\n"
            f"⚠️ <b>Функция не реализована:</b> Переключение уровней доступа в данный момент не поддерживается.\n\n"
            f"• <code>/level_info</code> - информация об уровне"
        )

        from apps.edge.telegram_bot.bot_utils import build_switch_level_menu

        menu = build_switch_level_menu(access_level)

        try:
            await query.edit_message_text(
                switch_text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("🔄 Переключение уровня", show_alert=False)
            else:
                raise edit_error

    async def _handle_list_users(self, query, context):
        """Список пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return

        try:
            all_users = self.bot_db.get_all_users()

            users_text = f"👤 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b> (всего: {len(all_users)})\n\n"

            for user_data in all_users[:10]:  # Показываем первых 10 пользователей
                username = user_data.get("username") or "Без username"
                first_name = user_data.get("first_name") or "Без имени"
                user_access_level = user_data.get("access_level", "user")
                is_active = user_data.get("is_active", True)

                status_emoji = "✅" if is_active else "❌"
                level_emoji = {
                    "user": "👤",
                    "operator": "👷",
                    "engineer": "🔧",
                    "admin": "👑",
                }.get(user_access_level, "❓")

                users_text += (
                    f"{status_emoji} {level_emoji} <b>{first_name}</b> (@{username})\n"
                )
                users_text += f"   ID: <code>{user_data['telegram_id']}</code> | Уровень: <code>{user_access_level}</code>\n\n"

            if len(all_users) > 10:
                users_text += f"... и еще {len(all_users) - 10} пользователей\n"

            from apps.edge.telegram_bot.bot_utils import build_user_management_menu

            menu = build_user_management_menu(access_level)

            await query.edit_message_text(
                users_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка пользователей: {e}")
            await query.answer(
                "❌ Ошибка получения списка пользователей", show_alert=True
            )

    async def _handle_temp_level(self, query, context, level):
        """Установка временного уровня"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return

        await query.answer(
            f"⚠️ Функция переключения уровней не реализована",
            show_alert=True,
        )

    async def _handle_restore_level(self, query, context):
        """Восстановление оригинального уровня"""
        await query.answer(
            "⚠️ Функция переключения уровней не реализована",
            show_alert=True,
        )

    async def _handle_level_info_menu(self, query, context):
        """Информация о текущем уровне доступа"""
        user = query.from_user

        # Упрощенная информация без новых методов
        try:
            current_level = self.bot_db.get_user_access_level(user.id)

            info_text = "ℹ️ <b>ИНФОРМАЦИЯ ОБ УРОВНЕ ДОСТУПА</b>\n\n"
            info_text += f"📊 <b>Текущий уровень:</b> <code>{current_level}</code>\n"
            info_text += "⚡ <b>Статус:</b> Постоянный\n"

            # Показываем права доступа
            permissions = self.bot_db.get_access_permissions(current_level)
            if permissions:
                info_text += "\n🔓 <b>Ваши права:</b>\n"
                if permissions.get("can_read"):
                    info_text += "• ✅ Чтение данных\n"
                if permissions.get("can_write"):
                    info_text += "• ✅ Запись команд\n"
                if permissions.get("can_reset_alarms"):
                    info_text += "• ✅ Сброс аварий\n"

            info_text += "\n💡 <b>Команды переключения:</b>\n"
            info_text += "• <code>/switch_level user</code> - временно стать user\n"
            info_text += "• <code>/level_info</code> - подробная информация\n"

            from apps.edge.telegram_bot.bot_utils import build_switch_level_menu

            menu = build_switch_level_menu(current_level)

            await query.edit_message_text(
                info_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об уровне: {e}")
            await query.answer("❌ Ошибка получения информации", show_alert=True)

    # Настройки системы (сводка конфигурации)
    async def _handle_system_config(self, query, context):
        try:
            from core.config_manager import get_config

            cfg = get_config()
            data = await self.get_current_data_from_db() or {}
            do1 = data.get("digital_outputs_1")
            do2 = data.get("digital_outputs_2")
            do3 = data.get("digital_outputs_3")
            # Alarm relay summary
            ar = getattr(cfg, "alarm_relay", None)
            if ar and getattr(ar, "enabled", False):
                reg = str(getattr(ar, "register", "0x0082"))
                bit = int(getattr(ar, "bit", 7))
                relay_state = data.get("alarm_relay")
                ar_text = f"Включено ({reg}, бит {bit}) — текущее: {'ВКЛ' if relay_state else 'ВЫКЛ'}"
            else:
                ar_text = "Отключено"
            # Sensors
            sensors = getattr(cfg, "sensors", {}) or {}
            sensors_lines = []
            for key, enabled in sensors.items():
                sensors_lines.append(f"• {key}: {'вкл' if enabled else 'выкл'}")
            # System outputs
            outputs = getattr(cfg, "system_outputs", []) or []
            if outputs:
                reg_map = {"0x0081": do1, "0x0082": do2, "0x00a2": do3, "0x00A2": do3}
                out_lines = []
                for o in outputs:
                    if not o.enabled:
                        continue
                    val = reg_map.get(str(o.register))
                    state = None
                    if isinstance(val, int):
                        try:
                            state = ((val >> int(o.bit)) & 1) == 1
                        except Exception:
                            state = None
                    out_lines.append(
                        f"• {o.label}: {'ВКЛ' if state else ('ВЫКЛ' if state is not None else '—')}"
                    )
                outputs_text = "\n".join(out_lines) if out_lines else "—"
            else:
                outputs_text = "—"
            text = (
                "⚙️ <b>НАСТРОЙКИ СИСТЕМЫ (сводка)</b>\n\n"
                f"🔐 Аварийное реле: {ar_text}\n\n"
                f"🧩 Датчики (вывод в UI):\n"
                + ("\n".join(sensors_lines) or "—")
                + "\n\n"
                f"🧲 Системные выходы:\n{outputs_text}\n\n"
                "Изменение настроек из бота пока отключено (read‑only)."
            )
            from apps.edge.telegram_bot.bot_utils import build_settings_menu

            menu = build_settings_menu(
                self.bot_db.get_user_access_level(query.from_user.id)
            )
            await query.edit_message_text(
                text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка показа настроек: {e}")
            await query.answer("❌ Ошибка отображения настроек", show_alert=True)

    # Системные логи/сводка (краткий технический отчёт)
    async def _handle_system_logs(self, query, context):
        try:
            data = await self.get_current_data_from_db() or {}
            alarms = int(data.get("active_alarms", 0) or 0)
            warns = int(data.get("active_warnings", 0) or 0)
            relay_on = bool(data.get("alarm_relay")) if "alarm_relay" in data else False
            updated = data.get("updated_at") or "—"
            # Очередь команд записи
            recent = self.get_recent_write_commands(limit=5)
            lines = []
            for c in recent:
                cid = str(c.get("id"))[:8]
                reg = int(c.get("register", 0) or 0)
                st = c.get("status")
                when = c.get("executed_at") or c.get("created_at") or ""
                icon = (
                    "✅"
                    if st == "completed"
                    else ("⏳" if st in ("pending", "executing") else "❌")
                )
                lines.append(f"{icon} {cid} 0x{reg:04X} [{st}] {when}")
            queue_text = "\n".join(lines) if lines else "—"
            text = (
                "📋 <b>Системная сводка</b>\n\n"
                f"⏱ Обновлено: <code>{updated}</code>\n"
                f"🚨 Аварии: {alarms} | ⚠️ Предупреждения: {warns} | {('Реле ВКЛ' if relay_on else 'Реле ВЫКЛ')}\n\n"
                f"📝 Последние команды записи:\n{queue_text}"
            )
            from apps.edge.telegram_bot.bot_utils import build_settings_menu

            menu = build_settings_menu(
                self.bot_db.get_user_access_level(query.from_user.id)
            )
            await query.edit_message_text(
                text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка показа сводки логов: {e}")
            await query.answer("❌ Ошибка отображения сводки", show_alert=True)

    async def _handle_permissions_config(self, query, context):
        await query.answer("🔐 Управление правами - в разработке", show_alert=True)

    async def _handle_backup_config(self, query, context):
        await query.answer("💾 Резервные копии - в разработке", show_alert=True)

    async def _handle_invite_user(self, query, context):
        """Приглашение пользователя - выбор уровня доступа"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для приглашения пользователей", show_alert=True
            )
            return

        invite_text = (
            f"➕ <b>ПРИГЛАШЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"🔐 <b>Ваш уровень:</b> <code>{access_level}</code>\n\n"
            f"Выберите уровень доступа для нового пользователя:\n\n"
            f"<b>Доступные уровни:</b>\n"
            f"• <b>👤 User</b> - только чтение данных\n"
            f"• <b>⚙️ Operator</b> - чтение + запись команд\n"
            f"• <b>🔧 Engineer</b> - расширенные функции\n\n"
            f"После выбора будет создана уникальная ссылка-приглашение."
        )

        from apps.edge.telegram_bot.bot_utils import build_invitation_level_menu

        menu = build_invitation_level_menu()

        try:
            await query.edit_message_text(
                invite_text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("➕ Приглашение пользователя", show_alert=False)
            else:
                raise edit_error

    async def _handle_block_user(self, query, context):
        """Блокировка пользователя"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для блокировки пользователей", show_alert=True
            )
            return

        try:
            all_users = self.bot_db.get_all_users()
            active_users = [u for u in all_users if u.get("is_active", True)]

            if not active_users:
                await query.answer(
                    "❌ Нет активных пользователей для блокировки", show_alert=True
                )
                return

            block_text = (
                "🔒 <b>БЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
                "<b>Нажмите на пользователя для блокировки:</b>\n\n"
                "⚠️ <b>Внимание:</b> Заблокированный пользователь не сможет использовать бота до разблокировки."
            )

            from apps.edge.telegram_bot.bot_utils import build_user_list_menu

            menu = build_user_list_menu(active_users, "block", access_level)

            await query.edit_message_text(
                block_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка для блокировки: {e}")
            await query.answer(
                "❌ Ошибка получения списка пользователей", show_alert=True
            )

    async def _handle_unblock_user(self, query, context):
        """Разблокировка пользователя"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для разблокировки пользователей", show_alert=True
            )
            return

        try:
            all_users = self.bot_db.get_all_users()
            blocked_users = [u for u in all_users if not u.get("is_active", True)]

            if not blocked_users:
                unblock_text = (
                    "✅ <b>РАЗБЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
                    "🎉 <b>Все пользователи активны!</b>\n\n"
                    "В системе нет заблокированных пользователей."
                )

                from apps.edge.telegram_bot.bot_utils import build_user_management_menu

                menu = build_user_management_menu(access_level)

                await query.edit_message_text(
                    unblock_text, reply_markup=menu, parse_mode="HTML"
                )
            else:
                unblock_text = (
                    "✅ <b>РАЗБЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
                    "<b>Нажмите на пользователя для разблокировки:</b>"
                )

                from apps.edge.telegram_bot.bot_utils import build_user_list_menu

                menu = build_user_list_menu(blocked_users, "unblock", access_level)

                await query.edit_message_text(
                    unblock_text, reply_markup=menu, parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка для разблокировки: {e}")
            await query.answer(
                "❌ Ошибка получения списка пользователей", show_alert=True
            )

    async def _handle_change_permissions(self, query, context):
        """Изменение прав пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level != "admin":
            await query.answer(
                "❌ Только администраторы могут изменять права", show_alert=True
            )
            return

        try:
            all_users = self.bot_db.get_all_users()

            if not all_users:
                await query.answer("❌ Пользователи не найдены", show_alert=True)
                return

            permissions_text = (
                "👑 <b>ИЗМЕНЕНИЕ ПРАВ ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
                "<b>Нажмите на пользователя для изменения его прав:</b>\n\n"
                "<b>Доступные уровни:</b>\n"
                "• 👤 <code>user</code> - только чтение\n"
                "• 👷 <code>operator</code> - чтение + запись\n"
                "• 🔧 <code>engineer</code> - расширенные функции\n"
                "• 👑 <code>admin</code> - полный доступ"
            )

            from apps.edge.telegram_bot.bot_utils import build_user_list_menu

            menu = build_user_list_menu(all_users, "promote", access_level)

            await query.edit_message_text(
                permissions_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о правах: {e}")
            await query.answer("❌ Ошибка получения информации", show_alert=True)

    async def _handle_user_stats(self, query, context):
        """Статистика пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для просмотра статистики", show_alert=True
            )
            return

        try:
            all_users = self.bot_db.get_all_users()

            if not all_users:
                await query.answer("❌ Пользователи не найдены", show_alert=True)
                return

            # Подсчитываем статистику
            total_users = len(all_users)
            active_users = sum(1 for u in all_users if u.get("is_active", True))
            inactive_users = total_users - active_users

            # Статистика по уровням доступа
            level_stats = {}
            for user_data in all_users:
                level = user_data.get("access_level", "user")
                level_stats[level] = level_stats.get(level, 0) + 1

            stats_text = "📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            stats_text += f"👥 <b>Всего пользователей:</b> {total_users}\n"
            stats_text += f"✅ <b>Активных:</b> {active_users}\n"
            stats_text += f"❌ <b>Неактивных:</b> {inactive_users}\n\n"

            stats_text += "<b>📊 По уровням доступа:</b>\n"
            level_emojis = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}
            for level, count in level_stats.items():
                emoji = level_emojis.get(level, "❓")
                stats_text += f"{emoji} <b>{level.capitalize()}:</b> {count} чел.\n"

            # Показываем последнюю активность
            recent_users = [u for u in all_users if u.get("last_active")][:5]
            if recent_users:
                stats_text += "\n<b>🕐 Последняя активность:</b>\n"
                for user_data in recent_users:
                    username = user_data.get("username") or "Без username"
                    last_active = user_data.get("last_active", "неизвестно")
                    stats_text += f"• @{username} - {last_active}\n"

            # Получаем детальную статистику от базы данных
            stats_text += "\n<b>📈 Активность системы:</b>\n"

            # Подсчитываем команды из истории
            try:
                import sqlite3

                from core.config_manager import get_config
                with sqlite3.connect(get_config().database.commands_db) as conn:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM user_command_history WHERE timestamp > datetime('now', '-24 hours')"
                    )
                    commands_24h = cursor.fetchone()[0]

                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM user_command_history WHERE timestamp > datetime('now', '-1 hour')"
                    )
                    commands_1h = cursor.fetchone()[0]

                    stats_text += f"• Команд за час: {commands_1h}\n"
                    stats_text += f"• Команд за сутки: {commands_24h}\n"
            except:
                stats_text += "• Статистика команд недоступна\n"

            from apps.edge.telegram_bot.bot_utils import build_user_management_menu

            menu = build_user_management_menu(access_level)

            await query.edit_message_text(
                stats_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователей: {e}")
            await query.answer("❌ Ошибка получения статистики", show_alert=True)

    # =======================================================================
    # ИНТЕРАКТИВНЫЕ ОБРАБОТЧИКИ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ
    # =======================================================================

    async def _handle_promote_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для изменения прав"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level != "admin":
            await query.answer(
                "❌ Только администраторы могут изменять права", show_alert=True
            )
            return

        try:
            # Получаем информацию о выбранном пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return

            target_username = target_user.get("username", "Без username")
            target_first_name = target_user.get("first_name", "Без имени")
            current_level = target_user.get("access_level", "user")

            # Не позволяем изменять права самому себе
            if user_id == user.id:
                await query.answer(
                    "❌ Вы не можете изменить свои собственные права", show_alert=True
                )
                return

            level_emojis = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}
            current_emoji = level_emojis.get(current_level, "❓")

            promote_text = (
                f"👑 <b>ИЗМЕНЕНИЕ ПРАВ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
                f"<b>Выбранный пользователь:</b>\n"
                f"{current_emoji} <b>{target_first_name}</b> (@{target_username})\n"
                f"<b>Текущий уровень:</b> <code>{current_level}</code>\n\n"
                f"<b>Выберите новый уровень доступа:</b>"
            )

            from apps.edge.telegram_bot.bot_utils import build_level_selection_menu

            menu = build_level_selection_menu(user_id, current_level)

            await query.edit_message_text(
                promote_text, reply_markup=menu, parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка выбора пользователя для изменения прав: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_set_user_level(
        self, query, context, user_id: int, new_level: str
    ):
        """Установка нового уровня доступа пользователю"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level != "admin":
            await query.answer(
                "❌ Только администраторы могут изменять права", show_alert=True
            )
            return

        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return

            target_username = target_user.get("username", "Без username")
            target_first_name = target_user.get("first_name", "Без имени")
            old_level = target_user.get("access_level", "user")

            # Обновляем уровень доступа напрямую в базе данных
            try:
                from core.config_manager import get_config
                with sqlite3.connect(get_config().database.commands_db) as conn:
                    cursor = conn.execute(
                        """
                        UPDATE telegram_users
                        SET access_level = ?, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """,
                        (new_level, user_id),
                    )

                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при изменении уровня: {db_error}")
                success = False

            if success:
                level_emojis = {
                    "user": "👤",
                    "operator": "👷",
                    "engineer": "🔧",
                    "admin": "👑",
                }
                old_emoji = level_emojis.get(old_level, "❓")
                new_emoji = level_emojis.get(new_level, "❓")

                success_text = (
                    f"✅ <b>ПРАВА ПОЛЬЗОВАТЕЛЯ ИЗМЕНЕНЫ</b>\n\n"
                    f"<b>Пользователь:</b> {target_first_name} (@{target_username})\n"
                    f"<b>Изменение:</b> {old_emoji} <code>{old_level}</code> → {new_emoji} <code>{new_level}</code>\n"
                    f"<b>Изменил:</b> @{user.username or 'Unknown'}\n\n"
                    f"Изменения вступили в силу немедленно."
                )

                from apps.edge.telegram_bot.bot_utils import build_user_management_menu

                menu = build_user_management_menu(access_level)

                await query.edit_message_text(
                    success_text, reply_markup=menu, parse_mode="HTML"
                )

                await query.answer("✅ Права пользователя изменены", show_alert=False)
            else:
                await query.answer(
                    "❌ Ошибка изменения прав пользователя", show_alert=True
                )

        except Exception as e:
            logger.error(f"❌ Ошибка установки уровня пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_block_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для блокировки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для блокировки пользователей", show_alert=True
            )
            return

        # Проверяем, что пользователь не блокирует самого себя
        if user_id == user.id:
            await query.answer(
                "❌ Вы не можете заблокировать самого себя", show_alert=True
            )
            return

        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return

            target_username = target_user.get("username", "Без username")
            target_first_name = target_user.get("first_name", "Без имени")

            # Блокируем пользователя
            success = self.bot_db.deactivate_user(user_id)

            if success:
                block_text = (
                    f"🔒 <b>ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН</b>\n\n"
                    f"<b>Пользователь:</b> {target_first_name} (@{target_username})\n"
                    f"<b>Заблокировал:</b> @{user.username or 'Unknown'}\n\n"
                    f"Пользователь больше не сможет использовать бота до разблокировки."
                )

                from apps.edge.telegram_bot.bot_utils import build_user_management_menu

                menu = build_user_management_menu(access_level)

                await query.edit_message_text(
                    block_text, reply_markup=menu, parse_mode="HTML"
                )

                await query.answer("🔒 Пользователь заблокирован", show_alert=False)
            else:
                await query.answer("❌ Ошибка блокировки пользователя", show_alert=True)

        except Exception as e:
            logger.error(f"❌ Ошибка блокировки пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_unblock_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для разблокировки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для разблокировки пользователей", show_alert=True
            )
            return

        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return

            target_username = target_user.get("username", "Без username")
            target_first_name = target_user.get("first_name", "Без имени")

            # Разблокируем пользователя
            try:
                with sqlite3.connect("kub_commands.db") as conn:
                    cursor = conn.execute(
                        """
                        UPDATE telegram_users
                        SET is_active = 1, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """,
                        (user_id,),
                    )

                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при разблокировке: {db_error}")
                success = False

            if success:
                unblock_text = (
                    f"✅ <b>ПОЛЬЗОВАТЕЛЬ РАЗБЛОКИРОВАН</b>\n\n"
                    f"<b>Пользователь:</b> {target_first_name} (@{target_username})\n"
                    f"<b>Разблокировал:</b> @{user.username or 'Unknown'}\n\n"
                    f"Пользователь снова может использовать бота."
                )

                from apps.edge.telegram_bot.bot_utils import build_user_management_menu

                menu = build_user_management_menu(access_level)

                await query.edit_message_text(
                    unblock_text, reply_markup=menu, parse_mode="HTML"
                )

                await query.answer("✅ Пользователь разблокирован", show_alert=False)
            else:
                await query.answer(
                    "❌ Ошибка разблокировки пользователя", show_alert=True
                )

        except Exception as e:
            logger.error(f"❌ Ошибка разблокировки пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    # =======================================================================
    # ЗАПУСК БЕЗ КОНФЛИКТОВ
    # =======================================================================

    async def start_bot(self):
        """Исправленный запуск бота БЕЗ создания собственной системы RS485"""
        try:
            logger.info("🚀 Инициализация Telegram Bot (без RS485)...")

            # Инициализируем только базы данных
            from apps.edge.modbus.modbus_storage import init_db

            init_db()

            # Создаём приложение Telegram
            self.application = Application.builder().token(self.token).build()

            # Регистрируем обработчики команд
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            # Управление авариями
            self.application.add_handler(CommandHandler("reset", self.cmd_reset))
            self.application.add_handler(CommandHandler("alarms", self.cmd_alarms))
            self.application.add_handler(CommandHandler("queue", self.cmd_queue))
            self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))

            # УПРАВЛЕНИЕ РОЛЯМИ
            self.application.add_handler(CommandHandler("promote", self.cmd_promote))
            self.application.add_handler(CommandHandler("users", self.cmd_users))

            # ПЕРЕКЛЮЧЕНИЕ УРОВНЕЙ ДОСТУПА (не реализовано)
            # self.application.add_handler(
            #     CommandHandler("switch_level", self.cmd_switch_level)
            # )
            # self.application.add_handler(
            #     CommandHandler("level_info", self.cmd_level_info)
            # )

            # БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ
            self.application.add_handler(
                CommandHandler("block_user", self.cmd_block_user)
            )
            self.application.add_handler(
                CommandHandler("unblock_user", self.cmd_unblock_user)
            )

            # Обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))

            logger.info("🚀 Запуск Telegram Bot...")

            # Инициализируем приложение
            await self.application.initialize()
            await self.application.start()

            # Запускаем polling вручную для лучшего контроля
            await self.application.updater.start_polling(drop_pending_updates=True)

            # Фоновая задача мониторинга аварий
            try:
                self.application.job_queue.run_repeating(
                    self._alarm_watch_job, interval=40, first=10, name="alarm_watch"
                )
                logger.info("🛰️ Запущен фоновый мониторинг аварий")
            except Exception as jerr:
                logger.warning(f"⚠️ Не удалось запустить фоновый мониторинг: {jerr}")

            logger.info("🤖 Бот запущен и ждет сообщения...")

            # Проверяем истекшие временные уровни доступа (временно отключено)
            try:
                expired_count = self.bot_db.check_and_restore_expired_levels()
                if expired_count > 0:
                    logger.info(
                        f"⏰ Восстановлено {expired_count} истекших временных уровней доступа"
                    )
            except AttributeError:
                logger.debug("Функциональность переключения уровней не реализована")

            try:
                # Ждем бесконечно
                await asyncio.sleep(float("inf"))
            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал остановки...")
            finally:
                # Корректная остановка
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise

    async def _handle_invite_level_selected(self, query, context, level: str):
        """Обработка выбора уровня доступа для приглашения"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return

        # Проверяем доступность выбранного уровня
        if level == "engineer" and access_level not in ["engineer", "admin"]:
            await query.answer(
                "❌ Недостаточно прав для создания Engineer приглашения", show_alert=True
            )
            return

        level_names = {
            "user": "User (Пользователь)",
            "operator": "Operator (Оператор)",
            "engineer": "Engineer (Инженер)",
        }

        confirmation_text = (
            f"✅ <b>ПОДТВЕРЖДЕНИЕ ПРИГЛАШЕНИЯ</b>\n\n"
            f"🎯 <b>Уровень доступа:</b> <code>{level_names.get(level, level)}</code>\n"
            f"⏰ <b>Срок действия:</b> 24 часа\n"
            f"👤 <b>Приглашает:</b> @{user.username}\n\n"
            f"Создать уникальную ссылку-приглашение?"
        )

        from apps.edge.telegram_bot.bot_utils import build_invitation_confirmation_menu

        menu = build_invitation_confirmation_menu(level)

        try:
            await query.edit_message_text(
                confirmation_text, reply_markup=menu, parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("✅ Подтверждение приглашения", show_alert=False)
            else:
                raise edit_error

    async def _handle_confirm_invite(self, query, context, level: str):
        """Создание приглашения и генерация уникальной ссылки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)

        if access_level not in ["operator", "engineer", "admin"]:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return

        try:
            # Получаем имя бота для создания ссылки
            bot_username = (
                self.application.bot.username
                if hasattr(self, "application") and hasattr(self.application, "bot")
                else "your_bot"
            )

            # Временно создаём приглашение напрямую в базе (методы загрузятся после перезапуска)
            import datetime
            import sqlite3
            import uuid

            invitation_code = str(uuid.uuid4())[:8].upper()
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)

            # Прямая вставка в базу данных
            from core.config_manager import get_config
            conn = sqlite3.connect(get_config().database.commands_db)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO user_invitations (invitation_code, invited_by, access_level, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (invitation_code, user.id, level, expires_at.isoformat()),
            )

            conn.commit()
            conn.close()

            # Генерируем ссылку
            invite_link = f"https://t.me/{bot_username}?start=invite_{invitation_code}"

            level_names = {
                "user": "👤 User",
                "operator": "⚙️ Operator",
                "engineer": "🔧 Engineer",
            }

            # Первое сообщение - информация о приглашении
            info_text = (
                f"🎉 <b>ПРИГЛАШЕНИЕ СОЗДАНО</b>\n\n"
                f"📋 <b>Детали:</b>\n"
                f"• <b>Код:</b> <code>{invitation_code}</code>\n"
                f"• <b>Уровень:</b> {level_names.get(level, level)}\n"
                f"• <b>Срок действия:</b> 24 часа\n"
                f"• <b>Создал:</b> @{user.username}\n\n"
                f"📤 <b>Ссылка отправлена в следующем сообщении для удобного копирования</b>"
            )

            from apps.edge.telegram_bot.bot_utils import build_user_management_menu

            menu = build_user_management_menu(access_level)

            await query.edit_message_text(
                info_text, reply_markup=menu, parse_mode="HTML"
            )

            # Второе сообщение - только ссылка с кнопками для отправки
            link_text = (
                f"🔗 <b>Ссылка-приглашение:</b>\n\n"
                f"{invite_link}\n\n"
                f"📱 <b>Нажмите на ссылку выше для копирования</b>\n"
                f"📤 <b>Или используйте кнопки ниже для отправки</b>"
            )

            from apps.edge.telegram_bot.bot_utils import build_invitation_share_menu

            share_menu = build_invitation_share_menu(invite_link, access_level)

            await query.message.reply_text(
                link_text, reply_markup=share_menu, parse_mode="HTML"
            )

            logger.info(
                f"✅ Создано приглашение {invitation_code} для уровня {level} пользователем {user.id}"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка создания приглашения: {e}")
            from apps.edge.telegram_bot.bot_utils import build_user_management_menu

            menu = build_user_management_menu(access_level)

            await query.edit_message_text(
                error_message(f"Ошибка создания приглашения: {str(e)}"),
                reply_markup=menu,
                parse_mode="HTML",
            )


# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================


def main():
    """Основная функция запуска"""
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063 (ЦЕНТРАЛИЗОВАННАЯ КОНФИГУРАЦИЯ)")
    print("=" * 60)

    # Получаем токен через конфиг-менеджер
    token = config.telegram.token

    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN")
        print("💡 Добавьте токен в config/bot_secrets.json:")
        print('{"telegram": {"bot_token": "your_token", "admin_users": [your_id]}}')
        print("💡 Или установите переменную окружения TELEGRAM_BOT_TOKEN")
        return

    logger.info("✅ Токен загружен через ConfigManager")
    logger.info(f"📊 Администраторов: {len(config.telegram.admin_users)}")
    logger.info(f"⚙️ Сервисы включены: telegram={config.services.telegram_enabled}")

    # Создаём бота
    bot = KUBTelegramBot(token)

    try:
        import asyncio

        asyncio.run(bot.start_bot())

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()
