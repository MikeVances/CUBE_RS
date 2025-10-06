# CUBE_RS Web Interface

Modern FastAPI-based web interface for real-time Modbus monitoring and device management.

## Features

### 🚀 **Real-time Monitoring**
- Live system statistics updates via WebSocket
- Real-time device status monitoring
- Performance metrics visualization with Chart.js

### 🔧 **Device Management**
- Register/unregister Modbus devices (TCP/RTU)
- Live device status with connection health
- Device configuration management

### 📊 **Modbus Operations**
- Interactive Modbus read/write operations
- Support for all standard function codes:
  - Read Holding Registers (3)
  - Read Input Registers (4)
  - Read Coils (1)  
  - Read Discrete Inputs (2)
  - Write Single Register (6)
  - Write Multiple Registers (16)

### 💻 **Modern UI**
- Bootstrap 5 responsive design
- Real-time charts and metrics
- WebSocket-powered live updates
- Mobile-friendly interface

## API Endpoints

### System Endpoints
- `GET /` - Main dashboard page
- `GET /api/health` - System health check
- `GET /api/stats` - Comprehensive system statistics
- `WS /ws` - WebSocket for real-time updates

### Device Management
- `GET /api/devices` - List all registered devices
- `POST /api/devices` - Register new device
- `DELETE /api/devices/{device_id}` - Unregister device

### Modbus Operations
- `POST /api/modbus/read` - Execute Modbus read request
- `POST /api/modbus/write` - Execute Modbus write request

## Quick Start

### 1. Start the Web Interface
```bash
# Using the startup script
poetry run python run_web.py

# Or directly
poetry run uvicorn web_interface.main:app --host 0.0.0.0 --port 8080 --reload
```

### 2. Access the Interface
Open your browser and navigate to: http://localhost:8080

### 3. Register a Device
Use the web interface or API:

```bash
curl -X POST http://localhost:8080/api/devices \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": 1,
    "name": "PLC Device",
    "connection_type": 1,
    "host": "192.168.1.100",
    "port": 502,
    "device_address": 1,
    "description": "Main PLC controller"
  }'
```

### 4. Execute Modbus Operations
```bash
# Read holding registers
curl -X POST http://localhost:8080/api/modbus/read \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": 1,
    "function_code": 3,
    "register_address": 0,
    "register_count": 10
  }'
```

## Configuration

Configuration is handled via environment variables:

```bash
# Server settings
WEB_HOST=0.0.0.0
WEB_PORT=8080
WEB_RELOAD=false

# Gateway settings  
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=5023
GATEWAY_DB_PATH=web_modbus_data.db
MAX_CONCURRENT_REQUESTS=20

# Security
SECRET_KEY=your-secret-key-here

# Monitoring
MONITORING_UPDATE_INTERVAL=2
MAX_CHART_POINTS=20
```

## Architecture

The web interface is built on:

- **FastAPI** - High-performance async web framework
- **WebSockets** - Real-time bidirectional communication
- **Bootstrap 5** - Modern responsive UI framework
- **Chart.js** - Interactive data visualization
- **TypedModbusGateway** - Direct integration with Modbus infrastructure

### Real-time Updates

The system provides real-time updates through WebSocket connections:
- System statistics every 2 seconds
- Device status changes
- Connection health monitoring
- Performance metrics

### Error Handling

Comprehensive error handling includes:
- Retry logic with exponential backoff
- Connection failure recovery
- Device health monitoring
- User-friendly error messages

## Integration

The web interface directly integrates with the CUBE_RS Modbus infrastructure:
- **TypedModbusGateway** for Modbus operations  
- **AsyncModbusClient** for device communication
- **Connection pooling** for efficient resource management
- **Database integration** for data persistence

## Security Features

- Environment-based configuration
- Input validation with Pydantic models
- Error message sanitization
- CORS support for cross-origin requests

## Development

### Running in Development Mode
```bash
# Enable auto-reload
WEB_RELOAD=true poetry run python run_web.py
```

### API Documentation
FastAPI provides automatic API documentation:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## Performance

The web interface is designed for high performance:
- Async/await throughout the stack
- Connection pooling for Modbus operations
- WebSocket connection management
- Efficient real-time data streaming

## Monitoring

Built-in monitoring includes:
- System uptime and health
- Device connection statistics
- Request/response metrics
- Error rates and response times
- Memory usage tracking