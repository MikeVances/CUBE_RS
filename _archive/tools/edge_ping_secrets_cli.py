#!/usr/bin/env python3
"""
EDGE Ping Secrets CLI

Управляет зашифрованным конфигом `edge_ping`:
{
  "servers": ["https://server-1.example/api/edge/ping", ...],
  "auth_token": "optional-jwt-or-api-key"
}

Примеры:
  python tools/edge_ping_secrets_cli.py show
  python tools/edge_ping_secrets_cli.py set-servers https://s1/api/edge/ping,https://s2/api/edge/ping
  python tools/edge_ping_secrets_cli.py set-token abc123
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.security_manager import SecurityManager


def load(sm: SecurityManager) -> Dict[str, Any]:
    try:
        return sm.load_encrypted_config("edge_ping")
    except Exception:
        return {}


def save(sm: SecurityManager, data: Dict[str, Any]) -> None:
    sm.save_encrypted_config("edge_ping", data)


def cmd_show(sm: SecurityManager) -> int:
    cfg = load(sm)
    servers = cfg.get("servers", [])
    token = cfg.get("auth_token", "")
    masked = (token[:3] + "***" + token[-3:]) if token and len(token) > 6 else ("***" if token else "")
    print("EDGE Ping config:")
    print(f"  Servers ({len(servers)}):")
    for s in servers:
        print(f"   - {s}")
    print(f"  Auth token: {masked}")
    return 0


def cmd_set_servers(sm: SecurityManager, csv: str) -> int:
    servers = [s.strip() for s in csv.split(",") if s.strip()]
    cfg = load(sm)
    cfg["servers"] = servers
    save(sm, cfg)
    print("✅ Servers updated")
    return 0


def cmd_set_token(sm: SecurityManager, token: str) -> int:
    cfg = load(sm)
    cfg["auth_token"] = token
    save(sm, cfg)
    print("✅ Auth token updated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EDGE Ping secrets manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("show")
    p1 = sub.add_parser("set-servers")
    p1.add_argument("csv")
    p2 = sub.add_parser("set-token")
    p2.add_argument("token")

    args = parser.parse_args()
    sm = SecurityManager(config_dir=str(_ROOT / "config"))

    if args.cmd == "show" or args.cmd is None:
        return cmd_show(sm)
    if args.cmd == "set-servers":
        return cmd_set_servers(sm, args.csv)
    if args.cmd == "set-token":
        return cmd_set_token(sm, args.token)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

