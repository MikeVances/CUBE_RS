"""
Deployment Gateway Module Aliases
Provides backward compatibility while eliminating code duplication.
"""

# Import all main modules with aliases for backward compatibility
# Note: modbus.gateway doesn't export ModbusGateway class - it's a script
from modbus.gateway_typed import TypedModbusGateway as DeployTypedGateway  # noqa: F401
from modbus.async_client import AsyncModbusClient as DeployAsyncClient  # noqa: F401
from modbus.modbus_storage import init_db, update_data  # noqa: F401

# Maintain backward compatibility - use TypedModbusGateway as the main gateway
ModbusGateway = DeployTypedGateway  # Alias for backward compatibility
TypedModbusGateway = DeployTypedGateway
AsyncModbusClient = DeployAsyncClient

# Storage functions as namespace
class ModbusStorage:
    """Storage functions namespace for backward compatibility."""
    init_db = staticmethod(init_db)
    update_data = staticmethod(update_data)

__all__ = [
    'ModbusGateway',
    'TypedModbusGateway', 
    'AsyncModbusClient',
    'ModbusStorage',
    'DeployGateway',
    'DeployTypedGateway',
    'DeployAsyncClient',
    'DeployStorage'
]