#!/usr/bin/env python3
"""
Telegram Secrets CLI - Управление секретами Telegram бота
Инструмент для безопасной настройки токенов и админов
"""

import argparse
import sys
from pathlib import Path

# Добавляем путь к core модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security_manager import get_security_manager

def show_secrets():
    """Показать замаскированные секреты"""
    try:
        sm = get_security_manager()
        secrets = sm.load_encrypted_config("bot_secrets")
        
        telegram_config = secrets.get("telegram", {})
        bot_token = telegram_config.get("bot_token", "НЕ УСТАНОВЛЕН")
        admin_users = telegram_config.get("admin_users", [])
        
        # Маскируем токен
        if bot_token and bot_token != "НЕ УСТАНОВЛЕН":
            masked_token = bot_token[:10] + "*" * 30 + bot_token[-10:]
        else:
            masked_token = bot_token
        
        print("🔐 Telegram секреты:")
        print(f"Bot Token: {masked_token}")
        print(f"Admin Users: {admin_users}")
        
    except FileNotFoundError:
        print("❌ Зашифрованные секреты не найдены")
        print("Создайте их с помощью: python telegram_secrets_cli.py set-token YOUR_TOKEN")
    except Exception as e:
        print(f"❌ Ошибка чтения секретов: {e}")

def set_token(token: str):
    """Установить токен бота"""
    try:
        sm = get_security_manager()
        
        # Загружаем существующие секреты или создаем новые
        try:
            secrets = sm.load_encrypted_config("bot_secrets")
        except FileNotFoundError:
            secrets = {}
        
        if "telegram" not in secrets:
            secrets["telegram"] = {}
        
        secrets["telegram"]["bot_token"] = token
        
        # Сохраняем зашифрованные секреты
        sm.save_encrypted_config("bot_secrets", secrets)
        
        print("✅ Токен бота сохранен в зашифрованном виде")
        print("📱 Теперь можно запускать бота")
        
        # Записываем событие безопасности
        sm.log_security_event("TELEGRAM_TOKEN_SET", details={"success": True})
        
    except Exception as e:
        print(f"❌ Ошибка сохранения токена: {e}")

def set_admins(admin_ids: str):
    """Установить список админов"""
    try:
        sm = get_security_manager()
        
        # Парсим ID админов
        admin_list = []
        for admin_id in admin_ids.split(","):
            admin_id = admin_id.strip()
            if admin_id.isdigit():
                admin_list.append(int(admin_id))
            else:
                print(f"⚠️ Неверный ID админа: {admin_id}")
        
        if not admin_list:
            print("❌ Не указаны валидные ID админов")
            return
        
        # Загружаем существующие секреты
        try:
            secrets = sm.load_encrypted_config("bot_secrets")
        except FileNotFoundError:
            secrets = {}
        
        if "telegram" not in secrets:
            secrets["telegram"] = {}
        
        secrets["telegram"]["admin_users"] = admin_list
        
        # Сохраняем
        sm.save_encrypted_config("bot_secrets", secrets)
        
        print(f"✅ Установлены админы: {admin_list}")
        
        # Записываем событие
        sm.log_security_event("TELEGRAM_ADMINS_SET", 
                             details={"admin_count": len(admin_list)})
        
    except Exception as e:
        print(f"❌ Ошибка сохранения админов: {e}")

def add_admin(admin_id: str):
    """Добавить админа"""
    try:
        if not admin_id.isdigit():
            print("❌ ID админа должен быть числом")
            return
        
        admin_id = int(admin_id)
        sm = get_security_manager()
        
        # Загружаем секреты
        try:
            secrets = sm.load_encrypted_config("bot_secrets")
        except FileNotFoundError:
            secrets = {"telegram": {"admin_users": []}}
        
        if "telegram" not in secrets:
            secrets["telegram"] = {"admin_users": []}
        
        admin_users = secrets["telegram"].get("admin_users", [])
        
        if admin_id in admin_users:
            print(f"⚠️ Админ {admin_id} уже есть в списке")
            return
        
        admin_users.append(admin_id)
        secrets["telegram"]["admin_users"] = admin_users
        
        sm.save_encrypted_config("bot_secrets", secrets)
        
        print(f"✅ Добавлен админ: {admin_id}")
        print(f"📝 Всего админов: {len(admin_users)}")
        
    except Exception as e:
        print(f"❌ Ошибка добавления админа: {e}")

def remove_admin(admin_id: str):
    """Удалить админа"""
    try:
        if not admin_id.isdigit():
            print("❌ ID админа должен быть числом")
            return
        
        admin_id = int(admin_id)
        sm = get_security_manager()
        
        # Загружаем секреты
        try:
            secrets = sm.load_encrypted_config("bot_secrets")
        except FileNotFoundError:
            print("❌ Секреты не найдены")
            return
        
        admin_users = secrets.get("telegram", {}).get("admin_users", [])
        
        if admin_id not in admin_users:
            print(f"⚠️ Админ {admin_id} не найден в списке")
            return
        
        admin_users.remove(admin_id)
        secrets["telegram"]["admin_users"] = admin_users
        
        sm.save_encrypted_config("bot_secrets", secrets)
        
        print(f"✅ Удален админ: {admin_id}")
        print(f"📝 Осталось админов: {len(admin_users)}")
        
    except Exception as e:
        print(f"❌ Ошибка удаления админа: {e}")

def export_env():
    """Экспорт переменных окружения"""
    try:
        sm = get_security_manager()
        secrets = sm.load_encrypted_config("bot_secrets")
        
        telegram_config = secrets.get("telegram", {})
        bot_token = telegram_config.get("bot_token")
        admin_users = telegram_config.get("admin_users", [])
        
        if bot_token:
            print(f"export TELEGRAM_BOT_TOKEN='{bot_token}'")
        
        if admin_users:
            admin_str = ",".join(str(uid) for uid in admin_users)
            print(f"export TELEGRAM_ADMIN_USERS='{admin_str}'")
        
        print("# Добавьте эти строки в ~/.bashrc или ~/.zshrc")
        print("# Или выполните: source <(python telegram_secrets_cli.py export-env)")
        
    except FileNotFoundError:
        print("❌ Секреты не настроены")
    except Exception as e:
        print(f"❌ Ошибка экспорта: {e}")

def main():
    parser = argparse.ArgumentParser(description="Управление секретами Telegram бота")
    subparsers = parser.add_subparsers(dest="command", help="Команды")
    
    # Показать секреты
    subparsers.add_parser("show", help="Показать замаскированные секреты")
    
    # Установить токен
    set_token_parser = subparsers.add_parser("set-token", help="Установить токен бота")
    set_token_parser.add_argument("token", help="Токен бота")
    
    # Установить админов
    set_admins_parser = subparsers.add_parser("set-admins", help="Установить список админов")
    set_admins_parser.add_argument("admin_ids", help="ID админов через запятую")
    
    # Добавить админа
    add_admin_parser = subparsers.add_parser("add-admin", help="Добавить админа")
    add_admin_parser.add_argument("admin_id", help="ID админа")
    
    # Удалить админа
    remove_admin_parser = subparsers.add_parser("remove-admin", help="Удалить админа")
    remove_admin_parser.add_argument("admin_id", help="ID админа")
    
    # Экспорт переменных
    subparsers.add_parser("export-env", help="Экспорт переменных окружения")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "show":
        show_secrets()
    elif args.command == "set-token":
        set_token(args.token)
    elif args.command == "set-admins":
        set_admins(args.admin_ids)
    elif args.command == "add-admin":
        add_admin(args.admin_id)
    elif args.command == "remove-admin":
        remove_admin(args.admin_id)
    elif args.command == "export-env":
        export_env()

if __name__ == "__main__":
    main()