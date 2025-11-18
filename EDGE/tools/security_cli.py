#!/usr/bin/env python3
"""CLI для управления безопасностью EDGE (мастер-пароль и вспомогательные операции)."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security_manager import get_security_manager


def _write_password_file(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(password.strip())
        fh.write("\n")
    os.chmod(path, 0o600)


def cmd_set_master_password(args: argparse.Namespace) -> int:
    sm = get_security_manager()
    secrets_dir = sm.secrets_dir
    master_key_file = secrets_dir / "master.key"
    master_password_file = secrets_dir / "master_password.txt"

    if master_key_file.exists() and not args.force:
        print(
            "❌ master.key уже создан. Сначала удалите существующий master.key/секреты или запустите с --force,"
            " если уверены."
        )
        return 2

    password = args.password
    if not password:
        pwd1 = getpass.getpass("Введите новый мастер-пароль: ")
        pwd2 = getpass.getpass("Повторите пароль: ")
        if not pwd1:
            print("❌ Пароль не может быть пустым")
            return 1
        if pwd1 != pwd2:
            print("❌ Пароли не совпадают")
            return 1
        password = pwd1

    _write_password_file(master_password_file, password)
    dev_password = secrets_dir / "dev_password.txt"
    if dev_password.exists():
        dev_password.unlink()
    print(f"✅ Мастер-пароль сохранён в {master_password_file}")
    if master_key_file.exists():
        print("⚠️ master.key уже существует. После изменения пароля пересоздайте master.key и секреты, если необходимо.")
    return 0


def cmd_remove_dev_password(_args: argparse.Namespace) -> int:
    sm = get_security_manager()
    dev_password = sm.secrets_dir / "dev_password.txt"
    if not dev_password.exists():
        print("ℹ️ dev_password.txt отсутствует")
        return 0
    dev_password.unlink()
    print("✅ dev_password.txt удалён")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Security CLI for EDGE secrets")
    sub = parser.add_subparsers(dest="command")

    p_set = sub.add_parser("set-master-password", help="Создать/обновить мастер-пароль для шифрования")
    p_set.add_argument("--password", help="Пароль (если не указан, будет запрошен интерактивно)")
    p_set.add_argument("--force", action="store_true", help="Игнорировать наличие master.key")
    p_set.set_defaults(func=cmd_set_master_password)

    p_rm = sub.add_parser("remove-dev-password", help="Удалить dev_password.txt, если он создан")
    p_rm.set_defaults(func=cmd_remove_dev_password)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
