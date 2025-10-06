"""
FastAPI Web Interface for CUBE_RS
Real-time Modbus monitoring and device management
Integrated with TypedModbusGateway
"""

import asyncio
import json
import logging

# Import our core types and gateway
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent))

from core.types import (
    DeviceId,
    ModbusConnectionInfo,
    ModbusConnectionType,
    ModbusDevice,
    ModbusFunctionCode,
    ModbusRequest,
)
from modbus.gateway_typed import TypedModbusGateway

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global gateway instance
gateway: Optional[TypedModbusGateway] = None


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"Client connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"Client disconnected. Total connections: {len(self.active_connections)}"
        )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message to websocket: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    global gateway
    logger.info("Starting CUBE_RS Web Interface...")

    # Initialize gateway
    gateway = TypedModbusGateway(
        host="127.0.0.1",
        port=5023,
        db_path="web_modbus_data.db",
        max_concurrent_requests=20,
    )

    # Initialize database
    await gateway._init_database()

    # Start background monitoring task
    background_task = asyncio.create_task(monitoring_task())

    logger.info("✅ CUBE_RS Web Interface started successfully")

    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down CUBE_RS Web Interface...")
        background_task.cancel()
        if gateway:
            await gateway.stop_server()
        logger.info("✅ CUBE_RS Web Interface shut down successfully")


# Initialize FastAPI app
app = FastAPI(
    title="CUBE_RS Web Interface",
    description="Real-time Modbus monitoring and device management",
    version="3.0.0",
    lifespan=lifespan,
)

# Configuration and paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Static files and templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Pydantic models for API
class DeviceConfig(BaseModel):
    device_id: DeviceId
    name: str
    connection_type: ModbusConnectionType
    host: str = "127.0.0.1"
    port: int = 502
    device_address: int = 1
    timeout: float = 5.0
    retry_count: int = 3
    enabled: bool = True
    description: Optional[str] = None


class ModbusReadRequest(BaseModel):
    device_id: DeviceId
    function_code: ModbusFunctionCode
    register_address: int
    register_count: int


class ModbusWriteRequest(BaseModel):
    device_id: DeviceId
    function_code: ModbusFunctionCode
    register_address: int
    register_count: int
    write_values: list[Union[int, bool]]


class SystemStats(BaseModel):
    uptime_seconds: float
    connected_devices: int
    total_requests: int
    successful_requests: int
    error_rate: float
    avg_response_time: float
    memory_usage_mb: float
    database_healthy: bool


# Background monitoring task
async def monitoring_task():
    """Background task to monitor system and broadcast updates"""
    while True:
        try:
            if gateway and manager.active_connections:
                # Get system stats
                stats = await get_system_stats()

                # Get device statuses
                devices_status = {}
                for device_id, device in gateway.modbus_client.device_registry.items():
                    devices_status[device_id] = {
                        "name": device.name,
                        "status": device.status.value,
                        "last_success": device.last_success.isoformat()
                        if device.last_success
                        else None,
                        "success_rate": device.success_rate,
                        "total_requests": device.total_requests,
                    }

                # Broadcast update
                update_data = {
                    "type": "system_update",
                    "timestamp": datetime.now().isoformat(),
                    "stats": stats.dict(),
                    "devices": devices_status,
                }

                await manager.broadcast(json.dumps(update_data))

            await asyncio.sleep(2)  # Update every 2 seconds

        except asyncio.CancelledError:
            logger.info("Monitoring task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in monitoring task: {e}")
            await asyncio.sleep(5)  # Wait before retrying


# Helper functions
async def get_system_stats() -> SystemStats:
    """Get comprehensive system statistics"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    uptime = (datetime.now() - gateway.start_time).total_seconds()
    connected_devices = len(gateway.modbus_client.device_registry)

    # Calculate success rate
    total_requests = gateway.request_counter
    successful_requests = total_requests - gateway.error_counter
    error_rate = (
        (gateway.error_counter / total_requests * 100) if total_requests > 0 else 0
    )

    # Average response time
    avg_response_time = (
        sum(gateway.response_times) / len(gateway.response_times)
        if gateway.response_times
        else 0
    )

    return SystemStats(
        uptime_seconds=uptime,
        connected_devices=connected_devices,
        total_requests=total_requests,
        successful_requests=successful_requests,
        error_rate=error_rate,
        avg_response_time=avg_response_time,
        memory_usage_mb=gateway._get_memory_usage(),
        database_healthy=await gateway._check_database_health(),
    )


# API Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    stats = await get_system_stats()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "stats": stats.dict(),
    }


@app.get("/api/devices")
async def list_devices():
    """List all registered devices"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    devices = []
    for device_id, device in gateway.modbus_client.device_registry.items():
        devices.append(
            {
                "device_id": device_id,
                "name": device.name,
                "connection_info": {
                    "type": device.connection_info.connection_type.value,
                    "host": device.connection_info.host,
                    "port": device.connection_info.port,
                    "device_address": device.connection_info.device_address,
                },
                "enabled": device.enabled,
                "status": device.status.value,
                "description": device.description,
                "last_success": device.last_success.isoformat()
                if device.last_success
                else None,
                "last_error": device.last_error,
                "total_requests": device.total_requests,
                "successful_requests": device.successful_requests,
                "success_rate": device.success_rate,
            }
        )

    return {"devices": devices}


@app.post("/api/devices")
async def register_device(device_config: DeviceConfig):
    """Register a new device"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    # Check if device already exists
    if device_config.device_id in gateway.modbus_client.device_registry:
        raise HTTPException(status_code=400, detail="Device already registered")

    # Create device
    connection_info = ModbusConnectionInfo(
        connection_type=device_config.connection_type,
        host=device_config.host,
        port=device_config.port,
        device_address=device_config.device_address,
        timeout=device_config.timeout,
        retry_count=device_config.retry_count,
    )

    device = ModbusDevice(
        device_id=device_config.device_id,
        name=device_config.name,
        connection_info=connection_info,
        description=device_config.description,
        enabled=device_config.enabled,
    )

    # Register device
    gateway.modbus_client.register_device(device)

    logger.info(f"Device {device_config.device_id} registered successfully")
    return {
        "message": "Device registered successfully",
        "device_id": device_config.device_id,
    }


@app.delete("/api/devices/{device_id}")
async def unregister_device(device_id: DeviceId):
    """Unregister a device"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    if device_id not in gateway.modbus_client.device_registry:
        raise HTTPException(status_code=404, detail="Device not found")

    gateway.modbus_client.unregister_device(device_id)
    logger.info(f"Device {device_id} unregistered successfully")
    return {"message": "Device unregistered successfully"}


@app.post("/api/modbus/read")
async def modbus_read(read_request: ModbusReadRequest):
    """Execute Modbus read request"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    try:
        request = ModbusRequest(
            device_id=read_request.device_id,
            function_code=read_request.function_code,
            register_address=read_request.register_address,
            register_count=read_request.register_count,
        )

        response = await gateway.modbus_client.execute_request(request)

        return {
            "success": response.success,
            "request": {
                "device_id": response.request.device_id,
                "function_code": response.request.function_code.value,
                "register_address": response.request.register_address,
                "register_count": response.request.register_count,
            },
            "data": response.data,
            "error_message": response.error_message,
            "response_time_ms": response.response_time_ms,
            "timestamp": response.timestamp.isoformat(),
        }

    except Exception as e:
        logger.error(f"Modbus read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/modbus/write")
async def modbus_write(write_request: ModbusWriteRequest):
    """Execute Modbus write request"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    try:
        request = ModbusRequest(
            device_id=write_request.device_id,
            function_code=write_request.function_code,
            register_address=write_request.register_address,
            register_count=write_request.register_count,
            write_values=write_request.write_values,
        )

        response = await gateway.modbus_client.execute_request(request)

        return {
            "success": response.success,
            "request": {
                "device_id": response.request.device_id,
                "function_code": response.request.function_code.value,
                "register_address": response.request.register_address,
                "register_count": response.request.register_count,
                "write_values": response.request.write_values,
            },
            "error_message": response.error_message,
            "response_time_ms": response.response_time_ms,
            "timestamp": response.timestamp.isoformat(),
        }

    except Exception as e:
        logger.error(f"Modbus write error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_statistics():
    """Get detailed system statistics"""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not available")

    stats = await get_system_stats()

    # Add connection pool stats
    connection_stats = gateway.modbus_client.get_connection_stats()

    return {"system": stats.dict(), "connections": connection_stats}


# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            logger.debug(f"Received websocket message: {data}")

            # Echo back for ping/pong
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True, log_level="info")
