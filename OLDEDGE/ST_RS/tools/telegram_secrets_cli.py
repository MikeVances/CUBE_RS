#!/usr/bin/env python3
"""
Telegram Secrets CLI (EDGE)

Назначение: управление зашифрованными секретами Telegram (токен и список админов),
используемыми ConfigManager/SecurityManager.

Основное:
- Хранилище: `config/secrets/bot_secrets.enc`
- Пароль для расшифровки: переменная окружения `CUBE_MASTER_PASSWORD`
- Перекрытие через ENV: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_USERS`

Примеры:
  # Показать секреты (токен маскируется)
  python tools/telegram_secrets_cli.py show

  # Установить токен
  python tools/telegram_secrets_cli.py set-token 123456:ABC-DEF...

  # Установить список админов (через запятую)
  python tools/telegram_secrets_cli.py set-admins 111111111,222222222

  # Добавить / удалить админа
  python tools/telegram_secrets_cli.py add-admin 333333333
  python tools/telegram_secrets_cli.py remove-admin 222222222

  # Инициализировать из JSON (формат: {"telegram": {"bot_token": "...", "admin_users": [..]}})
  python tools/telegram_secrets_cli.py init-from-file config/bot_secrets.json.backup

Подсказка:
  Запустите `python tools/telegram_secrets_cli.py help` для подробной справки.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Add EDGE root to Python path so 'core' module can be found
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.security_manager import SecurityManager


def load_encrypted(sm: SecurityManager) -> Dict[str, Any]:
    try:
        return sm.load_encrypted_config("bot_secrets")
    except FileNotFoundError:
        return {"telegram": {"bot_token": "", "admin_users": []}}


def save_encrypted(sm: SecurityManager, data: Dict[str, Any]) -> None:
    # Normalize structure
    if "telegram" not in data or not isinstance(data["telegram"], dict):
        data["telegram"] = {}
    tg = data["telegram"]
    tg.setdefault("bot_token", "")
    # admin_users may be list or string
    admins = tg.get("admin_users", [])
    if isinstance(admins, str):
        admins = [x.strip() for x in admins.split(",") if x.strip()]
    tg["admin_users"] = admins
    sm.save_encrypted_config("bot_secrets", data)
    
    # Синхронизируем с базой данных бота
    sync_admins_to_database(admins)


def sync_admins_to_database(admin_ids: List[str]) -> None:
    """Синхронизирует список админов из секретов с базой данных бота"""
    try:
        from apps.edge.telegram_bot.bot_database import TelegramBotDB
        
        # Путь к базе данных бота
        db_path = _ROOT / "data" / "kub_commands.db"
        db = TelegramBotDB(str(db_path))
        
        # Конвертируем админ IDs в int
        admin_ids_int = []
        for admin_id in admin_ids:
            try:
                admin_ids_int.append(int(admin_id))
            except ValueError:
                print(f"⚠️ Игнорируем неверный admin ID: {admin_id}")
                continue
        
        # Получаем текущих пользователей из базы
        current_users = db.get_all_users()
        current_admins = {user['telegram_id'] for user in current_users if user['access_level'] == 'admin'}
        
        # Определяем кого добавить/удалить
        new_admin_ids = set(admin_ids_int)
        to_add = new_admin_ids - current_admins
        to_demote = current_admins - new_admin_ids
        
        # Добавляем новых админов (или обновляем существующих до admin)
        for admin_id in to_add:
            existing_user = db.get_user(admin_id)
            if existing_user:
                # Пользователь существует - обновляем уровень
                db.set_user_access_level(admin_id, 'admin')
                print(f"✅ Пользователь {admin_id} повышен до admin")
            else:
                # Новый пользователь - регистрируем
                success = db.register_user(admin_id, f"admin_{admin_id}", f"Admin", None, 'admin')
                if success:
                    print(f"✅ Новый админ добавлен в базу: {admin_id}")
                else:
                    print(f"❌ Ошибка добавления админа {admin_id}")
        
        # Понижаем бывших админов до обычных пользователей
        for admin_id in to_demote:
            db.set_user_access_level(admin_id, 'user')
            print(f"📉 Админ {admin_id} понижен до уровня 'user'")
        
        if to_add or to_demote:
            print(f"🔄 Синхронизация завершена: +{len(to_add)} -{len(to_demote)} админов")
        
    except Exception as e:
        print(f"⚠️ Ошибка синхронизации с базой данных бота: {e}")


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 6:
        return "***"
    return token[:3] + "***" + token[-3:]


def cmd_show(sm: SecurityManager) -> int:
    data = load_encrypted(sm)
    tg = data.get("telegram", {})
    token = tg.get("bot_token", "")
    admins = tg.get("admin_users", [])
    if isinstance(admins, str):
        admins = [x.strip() for x in admins.split(",") if x.strip()]
    print("Telegram secrets:")
    print(f"  Token: {mask_token(token)}")
    print(f"  Admins: {admins if admins else '[]'}")
    return 0


def cmd_set_token(sm: SecurityManager, token: str) -> int:
    data = load_encrypted(sm)
    data.setdefault("telegram", {})["bot_token"] = token
    save_encrypted(sm, data)
    print("✅ Token updated")
    return 0


def cmd_set_admins(sm: SecurityManager, admins_csv: str) -> int:
    admins = [x.strip() for x in admins_csv.split(",") if x.strip()]
    data = load_encrypted(sm)
    data.setdefault("telegram", {})["admin_users"] = admins
    save_encrypted(sm, data)
    print(f"✅ Admins set: {admins}")
    return 0


def cmd_add_admin(sm: SecurityManager, admin_id: str) -> int:
    data = load_encrypted(sm)
    tg = data.setdefault("telegram", {})
    admins = tg.get("admin_users", [])
    if isinstance(admins, str):
        admins = [x.strip() for x in admins.split(",") if x.strip()]
    if admin_id not in admins:
        admins.append(admin_id)
    tg["admin_users"] = admins
    save_encrypted(sm, data)
    print(f"✅ Admin added: {admin_id}")
    return 0


def cmd_remove_admin(sm: SecurityManager, admin_id: str) -> int:
    data = load_encrypted(sm)
    tg = data.setdefault("telegram", {})
    admins = tg.get("admin_users", [])
    if isinstance(admins, str):
        admins = [x.strip() for x in admins.split(",") if x.strip()]
    admins = [a for a in admins if str(a) != str(admin_id)]
    tg["admin_users"] = admins
    save_encrypted(sm, data)
    print(f"✅ Admin removed: {admin_id}")
    return 0


def cmd_init_from_file(sm: SecurityManager, path: str) -> int:
    src = Path(path)
    if not src.exists():
        print(f"❌ File not found: {src}")
        return 1
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Invalid JSON: {e}")
        return 1
    save_encrypted(sm, data)
    print("✅ Encrypted secrets initialized from file")
    return 0


def cmd_sync(sm: SecurityManager) -> int:
    """Синхронизация админов из секретов в базу данных бота"""
    data = load_encrypted(sm)
    tg = data.get("telegram", {})
    admins = tg.get("admin_users", [])
    if isinstance(admins, str):
        admins = [x.strip() for x in admins.split(",") if x.strip()]
    
    print(f"Синхронизируем {len(admins)} админов из секретов...")
    sync_admins_to_database(admins)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="telegram_secrets_cli.py",
        description=(
            "Управление зашифрованными секретами Telegram (EDGE). "
            "Источник по умолчанию: config/secrets/bot_secrets.enc; "
            "переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_ADMIN_USERS перекрывают файл."
        ),
        epilog=(
            "Пароль для шифрования задаётся через CUBE_MASTER_PASSWORD. "
            "Хранилище: config/secrets/bot_secrets.enc."
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("help", help="Показать подробную справку")
    sub.add_parser("show", help="Показать текущие (маскированные) секреты из enc-файла")

    p1 = sub.add_parser("set-token", help="Установить токен бота в enc-файле")
    p1.add_argument("token")

    p2 = sub.add_parser("set-admins", help="Установить список админов (через запятую)")
    p2.add_argument("admins_csv", help="Comma-separated admin IDs")

    p3 = sub.add_parser("add-admin", help="Добавить одного админа по ID")
    p3.add_argument("admin_id")

    p4 = sub.add_parser("remove-admin", help="Удалить одного админа по ID")
    p4.add_argument("admin_id")

    p5 = sub.add_parser(
        "init-from-file",
        help=(
            "Инициализировать enc-файл из JSON (формат: {telegram: {bot_token, admin_users}})"
        ),
    )
    p5.add_argument("path", help="Путь к JSON-файлу с секретами")
    
    sub.add_parser("sync", help="Синхронизировать админов из секретов в базу данных бота")

    args = parser.parse_args()
    # Всегда работаем с EDGE/config
    sm = SecurityManager(config_dir=str(_ROOT / "config"))

    if args.cmd in (None, "help"):
        parser.print_help()
        print("\nПримеры:\n  python tools/telegram_secrets_cli.py show")
        print("  python tools/telegram_secrets_cli.py set-token 123456:ABC-DEF...")
        print("  python tools/telegram_secrets_cli.py set-admins 111111111,222222222")
        print("  python tools/telegram_secrets_cli.py add-admin 333333333")
        print("  python tools/telegram_secrets_cli.py remove-admin 222222222")
        print(
            "  python tools/telegram_secrets_cli.py init-from-file config/bot_secrets.json.backup"
        )
        print(
            "\nПриоритет источников: ENV (TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_USERS) → enc-файл."
        )
        print("Пароль для шифрования: CUBE_MASTER_PASSWORD.\n")
        return 0

    if args.cmd == "show":
        return cmd_show(sm)
    if args.cmd == "set-token":
        return cmd_set_token(sm, args.token)
    if args.cmd == "set-admins":
        return cmd_set_admins(sm, args.admins_csv)
    if args.cmd == "add-admin":
        return cmd_add_admin(sm, args.admin_id)
    if args.cmd == "remove-admin":
        return cmd_remove_admin(sm, args.admin_id)
    if args.cmd == "init-from-file":
        return cmd_init_from_file(sm, args.path)
    if args.cmd == "sync":
        return cmd_sync(sm)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
