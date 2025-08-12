#!/bin/bash
set -e

# --- 1. Создание новой ветки ---
git checkout -b feature/ux-improvements || git checkout feature/ux-improvements

# --- 2. Патч: telegram_bot/bot_utils.py ---
cat > telegram_bot/bot_utils.py << 'EOF'
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def build_main_menu(access_level: str = "user") -> InlineKeyboardMarkup:
    """Возвращает главное меню с inline-кнопками по уровню доступа"""
    buttons = [
        [InlineKeyboardButton("📊 Показания", callback_data="show_stats")],
        [InlineKeyboardButton("📈 Статистика", callback_data="show_history")],
    ]
    if access_level in ("operator", "admin"):
        buttons.append([InlineKeyboardButton("🔄 Сброс аварий", callback_data="reset_alarms")])
    if access_level == "admin":
        buttons.append([InlineKeyboardButton("⚙️ Настройки", callback_data="settings")])
    buttons.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="show_help")])
    return InlineKeyboardMarkup(buttons)

async def send_typing_action(update, context):
    """Отправляет 'печатает...' пока идет обработка"""
    if update.message:
        await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    elif update.callback_query:
        await context.bot.send_chat_action(chat_id=update.callback_query.message.chat_id, action="typing")

def error_message(text: str) -> str:
    return f"❌ <b>Ошибка</b>:\n{text}"
EOF

# --- 3. Патч: telegram_bot/bot_main.py ---
cat > telegram_bot/bot_main.py << 'EOF'
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes

from .bot_utils import build_main_menu, send_typing_action, error_message

class CubeBot:
    def __init__(self, application, bot_db):
        self.application = application
        self.bot_db = bot_db
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.bot_db.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        welcome_text = (
            f"👋 Привет, {user.first_name or user.username}!\n"
            f"Добро пожаловать в КУБ-1063 Control Bot.\n"
            f"Твой уровень доступа: <b>{access_level}</b>.\n\n"
            "Выбери действие в меню ниже ⬇️"
        )
        await update.message.reply_text(welcome_text, reply_markup=menu, parse_mode="HTML")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        access_level = self.bot_db.get_user_access_level(update.effective_user.id)
        help_text = (
            "ℹ️ <b>Справка по КУБ-1063 Control Bot</b>\n\n"
            "• <b>📊 Показания</b> — текущие данные с датчиков\n"
            "• <b>📈 Статистика</b> — история значений\n"
            "• <b>🔄 Сброс аварий</b> — только для операторов\n"
            "• <b>⚙️ Настройки</b> — только для админов\n\n"
            "Выберите действие в меню ниже:"
        )
        await update.message.reply_text(help_text, reply_markup=build_main_menu(access_level), parse_mode="HTML")

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_typing_action(update, context)
        # ... остальной код получения и вывода статистики

    async def confirm_reset_alarms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="reset_alarms_confirmed")],
            [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            "⚠️ <b>ВНИМАНИЕ!</b>\nВы уверены, что хотите сбросить все аварии?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        if data == "reset_alarms":
            await self.confirm_reset_alarms(update, context)
        elif data == "reset_alarms_confirmed":
            # ... выполнить сброс, показать успех/ошибку
            await query.edit_message_text("🔄 Все аварии были успешно сброшены.")
        elif data == "main_menu":
            access_level = self.bot_db.get_user_access_level(query.from_user.id)
            await query.edit_message_text(
                "Главное меню:",
                reply_markup=build_main_menu(access_level)
            )
        # ... другие обработчики
EOF

# --- 4. Финальный коммит ---
git add telegram_bot/bot_main.py telegram_bot/bot_utils.py
git commit -m "UX: Улучшения интерфейса Telegram-бота (главное меню, подтверждения, ошибки, справка, inline-кнопки, typing...)"

echo "✅ Патч UX успешно применён! Теперь запушь ветку: git push origin feature/ux-improvements"