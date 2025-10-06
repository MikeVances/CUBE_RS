"""
Type definitions for CUBE_RS system
Provides consistent typing across all modules
"""
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    Optional,
    Protocol,
    TypedDict,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    pass

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


# ===== MODBUS TYPES =====
class ModbusFunctionCode(IntEnum):
    """Supported Modbus function codes."""

    READ_COILS = 1
    READ_DISCRETE_INPUTS = 2
    READ_HOLDING_REGISTERS = 3
    READ_INPUT_REGISTERS = 4
    WRITE_SINGLE_COIL = 5
    WRITE_SINGLE_REGISTER = 6
    WRITE_MULTIPLE_COILS = 15
    WRITE_MULTIPLE_REGISTERS = 16


class ModbusConnectionType(IntEnum):
    """Modbus connection types."""

    TCP = 1
    RTU = 2
    ASCII = 3


class ModbusConnectionStatus(IntEnum):
    """Connection status for Modbus devices."""

    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3
    TIMEOUT = 4


class ModbusDataType(IntEnum):
    """Modbus data types for register interpretation."""

    INT16 = 1
    UINT16 = 2
    INT32 = 3
    UINT32 = 4
    FLOAT32 = 5
    BOOL = 6


DeviceId = int  # Type alias for device IDs (1-255)
RegisterAddress = int  # Type alias for register addresses (0-65535)
RegisterValue = Union[int, float, bool]  # Type alias for register values


@dataclass(frozen=True)
class ModbusConnectionInfo:
    """Modbus connection configuration."""

    connection_type: ModbusConnectionType
    host: str = "localhost"
    port: int = 502
    device_address: int = 1  # Slave address
    timeout: float = 5.0
    retry_count: int = 3

    def __post_init__(self) -> None:
        """Validate connection configuration."""
        if self.connection_type == ModbusConnectionType.TCP and self.port <= 0:
            raise ValueError("TCP port must be positive")
        if not (1 <= self.device_address <= 255):
            raise ValueError(f"Device address must be 1-255, got {self.device_address}")
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")


@dataclass
class ModbusDevice:
    """Modbus device with connection management."""

    device_id: DeviceId
    name: str
    connection_info: ModbusConnectionInfo
    description: Optional[str] = None
    enabled: bool = True
    status: ModbusConnectionStatus = ModbusConnectionStatus.DISCONNECTED
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    total_requests: int = 0
    successful_requests: int = 0

    def __post_init__(self) -> None:
        """Validate device configuration."""
        if not (1 <= self.device_id <= 255):
            raise ValueError(f"Device ID must be 1-255, got {self.device_id}")

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def is_healthy(self) -> bool:
        """Check if device is considered healthy."""
        return (
            self.enabled
            and self.status == ModbusConnectionStatus.CONNECTED
            and self.success_rate > 80.0
        )


class ModbusRequest(BaseModel):
    """Validated Modbus request."""

    model_config = ConfigDict(frozen=True)

    device_id: DeviceId = Field(..., ge=1, le=255, description="Device ID (1-255)")
    function_code: ModbusFunctionCode = Field(..., description="Modbus function code")
    register_address: RegisterAddress = Field(
        ..., ge=0, le=65535, description="Starting register address"
    )
    register_count: int = Field(..., ge=1, le=125, description="Number of registers")
    write_values: Optional[list[RegisterValue]] = Field(
        None, description="Values to write (for write operations)"
    )

    def __str__(self) -> str:
        return f"ModbusRequest(device={self.device_id}, func={self.function_code}, addr={self.register_address}, count={self.register_count})"


class ModbusResponse(BaseModel):
    """Modbus operation response."""

    model_config = ConfigDict(frozen=True)

    request: ModbusRequest
    success: bool
    data: Optional[list[RegisterValue]] = None
    error_message: Optional[str] = None
    response_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def is_successful(self) -> bool:
        """Check if response is successful."""
        return self.success and self.error_message is None


# ===== DATABASE TYPES =====
class DatabaseRecord(TypedDict):
    """Database record structure."""

    id: int
    device_id: DeviceId
    function_code: int
    register_address: RegisterAddress
    data: str  # JSON serialized
    timestamp: str  # ISO format
    success: bool
    response_time_ms: Optional[float]
    error_message: Optional[str]


# ===== ASYNC PROTOCOLS =====
class AsyncDatabaseProtocol(Protocol):
    """Protocol for async database operations."""

    async def save_modbus_data(self, response: ModbusResponse) -> None:
        """Save Modbus response to database."""
        ...

    async def get_device_history(
        self, device_id: DeviceId, limit: int = 100
    ) -> list[DatabaseRecord]:
        """Get device history from database."""
        ...

    async def close(self) -> None:
        """Close database connection."""
        ...


class AsyncModbusClientProtocol(Protocol):
    """Protocol for async Modbus clients."""

    async def read_registers(self, request: ModbusRequest) -> ModbusResponse:
        """Read Modbus registers."""
        ...

    async def write_registers(self, request: ModbusRequest) -> ModbusResponse:
        """Write Modbus registers."""
        ...

    async def connect(self) -> bool:
        """Connect to Modbus device."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from Modbus device."""
        ...


# ===== TELEGRAM TYPES =====
class TelegramMessageType(IntEnum):
    """Telegram message types."""

    TEXT = 1
    PHOTO = 2
    DOCUMENT = 3
    COMMAND = 4
    CALLBACK = 5


class TelegramMessage(BaseModel):
    """Telegram message with validation."""

    chat_id: int
    message_type: TelegramMessageType
    content: str = Field(..., min_length=1, max_length=4096)
    reply_to_message_id: Optional[int] = None
    parse_mode: Optional[Literal["HTML", "Markdown", "MarkdownV2"]] = None

    def __str__(self) -> str:
        return f"TelegramMessage(chat={self.chat_id}, type={self.message_type}, len={len(self.content)})"


# ===== WEB TYPES =====
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Generic API response wrapper."""

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def success_response(cls, data: Optional[T] = None) -> "APIResponse[T]":
        """Create successful response."""
        return cls(success=True, data=data)

    @classmethod
    def error_response(cls, error: str) -> "APIResponse[None]":
        """Create error response."""
        return cls(success=False, error=error)


# ===== MONITORING TYPES =====
@dataclass(frozen=True)
class PerformanceMetric:
    """Performance metric data point."""

    name: str
    value: float
    timestamp: datetime
    tags: Optional[dict[str, str]] = None

    def __str__(self) -> str:
        tags_str = f" {self.tags}" if self.tags else ""
        return f"{self.name}={self.value}{tags_str} @{self.timestamp}"


class HealthStatus(IntEnum):
    """System health status."""

    HEALTHY = 1
    DEGRADED = 2
    UNHEALTHY = 3
    UNKNOWN = 4


@dataclass
class HealthCheck:
    """Health check result."""

    service_name: str
    status: HealthStatus
    details: Optional[str] = None
    response_time_ms: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self.status == HealthStatus.HEALTHY


# ===== EVENT TYPES =====
class EventType(IntEnum):
    """System event types."""

    DEVICE_CONNECTED = 1
    DEVICE_DISCONNECTED = 2
    MODBUS_READ = 3
    MODBUS_WRITE = 4
    MODBUS_ERROR = 5
    TELEGRAM_MESSAGE = 6
    SYSTEM_START = 7
    SYSTEM_STOP = 8
    HEALTH_CHECK = 9


@dataclass
class SystemEvent:
    """System event for monitoring and logging."""

    event_type: EventType
    device_id: Optional[DeviceId] = None
    message: str = ""
    data: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type.name,
            "device_id": self.device_id,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


# ===== ASYNC UTILITIES =====
AsyncCallable = Callable[..., Awaitable[Any]]
AsyncContextManager = Callable[..., Any]  # For async context managers


# ===== CONFIGURATION TYPES =====
class ServiceConfig(BaseModel):
    """Base configuration for services."""

    enabled: bool = True
    host: str = "localhost"
    port: int
    timeout_seconds: int = 30
    retry_count: int = 3

    def get_address(self) -> str:
        """Get full address string."""
        return f"{self.host}:{self.port}"


class ModbusGatewayConfig(ServiceConfig):
    """Modbus Gateway configuration."""

    port: int = 5023
    max_concurrent_connections: int = 100
    enable_metrics: bool = True
    enable_health_check: bool = True


class TelegramBotConfig(ServiceConfig):
    """Telegram Bot configuration."""

    port: int = 0  # Not applicable for Telegram
    token_env_var: str = "TELEGRAM_BOT_TOKEN"
    webhook_enabled: bool = False
    webhook_url: Optional[str] = None
    polling_timeout: int = 10


class DatabaseConfig(BaseModel):
    """Database configuration."""

    connection_string: str
    max_connections: int = 10
    query_timeout_seconds: int = 30
    enable_wal: bool = True
    enable_foreign_keys: bool = True


# ===== EXCEPTIONS =====
class CubeRSError(Exception):
    """Base exception for CUBE_RS system."""

    pass


class ModbusError(CubeRSError):
    """Modbus operation error."""

    def __init__(self, message: str, device_id: Optional[DeviceId] = None):
        super().__init__(message)
        self.device_id = device_id


class DatabaseError(CubeRSError):
    """Database operation error."""

    pass


class TelegramError(CubeRSError):
    """Telegram operation error."""

    def __init__(self, message: str, chat_id: Optional[int] = None):
        super().__init__(message)
        self.chat_id = chat_id


class ConfigurationError(CubeRSError):
    """Configuration error."""

    pass
