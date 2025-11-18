"""
apps.edge.storage

Thin re-exports to keep a stable EDGE namespace for storage access,
while code continues to live in `modbus.modbus_storage`.
"""

from apps.edge.modbus.modbus_storage import (
    init_db,
    update_data,
    add_history_record,
    read_data,
    get_db_health,
)

__all__ = [
    "init_db",
    "update_data",
    "add_history_record",
    "read_data",
    "get_db_health",
]

