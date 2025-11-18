#!/usr/bin/env python3
"""Интерактивный мастер первого запуска EDGE."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

EDGE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = EDGE_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"

sys.path.insert(0, str(EDGE_DIR))

from tools import security_cli, telegram_secrets_cli


def prompt_bool(message: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{message} {suffix} ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def ensure_master_password() -> None:
    secrets_dir = CONFIG_DIR / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    master_password_file = secrets_dir / "master_password.txt"

    if master_password_file.exists():
        print(f"ℹ️ Мастер-пароль уже сохранён в {master_password_file}")
        if not prompt_bool("Перезаписать мастер-пароль?", default=False):
            return

    password = getpass.getpass("Введите мастер-пароль (или оставьте пустым для отмены): ")
    if not password:
        print("⏭️ Шаг пропущен — используйте security_cli позже")
        return

    confirm = getpass.getpass("Повторите мастер-пароль: ")
    if password != confirm:
        print("❌ Пароли не совпадают, шаг пропущен")
        return

    args = SimpleNamespace(password=password, force=True)
    security_cli.cmd_set_master_password(args)


def cleanup_dev_password() -> None:
    dev_password_file = CONFIG_DIR / "secrets" / "dev_password.txt"
    if dev_password_file.exists() and prompt_bool(
        "Удалить dev_password.txt (рекомендуется для продакшена)?", default=True
    ):
        dev_password_file.unlink()
        print("✅ dev_password.txt удалён")


def configure_telegram_token() -> None:
    if not prompt_bool("Настроить TELEGRAM_BOT_TOKEN сейчас?", default=True):
        return
    token = getpass.getpass("Введите TELEGRAM_BOT_TOKEN: ").strip()
    if not token:
        print("⚠️ Токен не указан, шаг пропущен")
        return
    telegram_secrets_cli.set_token(token)

    if prompt_bool("Добавить admin_ids (через запятую)?", default=False):
        admins = input("Введите список admin ids: ").strip()
        if admins:
            telegram_secrets_cli.set_admins(admins)


def run_autoscan() -> None:
    if not prompt_bool("Запустить автоскан (start_edge.py --autoscan)?", default=False):
        return
    port = input("RS485 порт [/dev/ttyUSB0]: ").strip() or "/dev/ttyUSB0"
    start_id = input("Начальный ID [1]: ").strip() or "1"
    end_id = input("Конечный ID [40]: ").strip() or "40"
    cmd = [
        sys.executable,
        str(EDGE_DIR / "start_edge.py"),
        "--autoscan",
        "--rs485-port",
        port,
        "--scan-start",
        start_id,
        "--scan-end",
        end_id,
    ]
    print(f"▶️ {' '.join(cmd)}")
    subprocess.run(cmd, check=False)


def main() -> int:
    os.chdir(PROJECT_ROOT)
    print("\n=== EDGE First Start Wizard ===\n")
    ensure_master_password()
    cleanup_dev_password()
    configure_telegram_token()
    run_autoscan()
    print(
        "\n✅ Базовая подготовка завершена. Запустите EDGE командой:"
        "\n   python EDGE/start.py --offline" 
        "\n(добавьте нужные флаги по необходимости)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
