"""
EDGE package: on-farm (gateway-side) services.

Contains entrypoints and light wrappers that group together:
- Modbus RS485 unified system (reader + writer)
- Modbus TCP gateway
- Optional Telegram bot
- Optional local dashboard

This package does not duplicate logic — it reuses existing modules
from `modbus`, `apps/gateway`, and `telegram_bot` to keep changes minimal
while providing a clean namespace for the EDGE node.
"""

