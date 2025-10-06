# EDGE (On‑Farm) Stack

This document describes the logical grouping of on‑farm services (EDGE node) and how to run them from a single entrypoint without relocating implementation files.

## Components

- Modbus RS485 unified system (reader + writer) → populates SQLite (`kub_data.db`)
- Modbus TCP gateway → exposes selected registers over TCP
- Telegram Bot (optional)
- Local Dashboard via Streamlit (optional)

## Layout

```
apps/
  edge/
    __init__.py
    start.py               # EDGE launcher (single entrypoint)
    storage/__init__.py    # Re‑exports from modbus.modbus_storage
  gateway/
    start_typed_gateway.py # Gateway launcher (reused by EDGE)
    telegram_service/
      start.py             # Telegram launcher (reused by EDGE)
modbus/
  unified_system.py        # RS485 Reader+Writer
  modbus_storage.py        # SQLite storage implementation
```

Implementation was physically moved into `apps/edge`:

- `apps/edge/modbus` (moved from `modbus`)
- `apps/edge/gateway` (moved from `apps/gateway`)
- `apps/edge/telegram_bot` (moved from `telegram_bot`)

For backward compatibility inside this repo, lightweight shim modules remain at the old paths (`modbus/*`, `apps/gateway/*`, `telegram_bot/*`) that re-export from the new locations. This eases the transition to a separate repository for EDGE.

## Run

From project root:

```bash
python -m apps.edge.start
```

This will start:

- `modbus.unified_system` (always)
- `apps/gateway/start_typed_gateway.py` (always)
- `apps/gateway/telegram_service/start.py` if `services.telegram_enabled: true`
- `dashboard/app.py` (Streamlit) if `services.dashboard_enabled: true` and Streamlit is available

Configuration is controlled via `config/app_config.yaml` and environment variables through `core.config_manager`. Security and shared utilities remain under `core/*` in this monorepo; in a split, copy `core/*` to the EDGE repo.

## Telegram Secrets

Encrypted secrets live in `config/secrets/bot_secrets.enc` and are managed by `core/security_manager.py`.

Preferred sources (priority):
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_USERS` in environment
- Encrypted file `config/secrets/bot_secrets.enc`

CLI to manage secrets:

```bash
# Show masked secrets
python tools/telegram_secrets_cli.py show

# Set token
python tools/telegram_secrets_cli.py set-token 123456:ABC-DEF...

# Set admin IDs (comma-separated)
python tools/telegram_secrets_cli.py set-admins 111111111,222222222

# Add / remove a single admin
python tools/telegram_secrets_cli.py add-admin 333333333
python tools/telegram_secrets_cli.py remove-admin 222222222

# Initialize encrypted secrets from plaintext JSON
python tools/telegram_secrets_cli.py init-from-file telegram_bot/bot_secrets.json
```

Notes:
- Provide `CUBE_MASTER_PASSWORD` via environment so SecurityManager can derive the key.
- A placeholder `config/bot_secrets.json` is kept to aid local setup; it references ENV variables and contains no secrets.

## Notes

- Storage API can be imported as `from apps.edge.storage import read_data, update_data, ...`.
- This structure is forward‑compatible with a future refactor that relocates storage and gateway into dedicated packages; call sites will remain stable under the `apps.edge.*` namespace.
