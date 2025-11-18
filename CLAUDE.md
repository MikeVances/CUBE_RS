# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CUBE_RS is a distributed industrial IoT monitoring system for CUBE controllers (КУБ-1063, КУБ-1112) with three independent deployable components:

- **EDGE**: Local industrial gateway for Modbus RTU/TCP communication with CUBE devices
- **SERVER**: Central authentication, device registry, and P2P tunnel broker
- **APP**: Mobile/web application backend with REST API

**Technology Stack**: Python 3.11+, Modbus (pymodbus), Flask, SQLite, WebRTC, Docker

## Architecture

The system follows a distributed three-tier architecture:

```
📱 Mobile/Web APP ↔ 🌐 SERVER (Auth/Tunnel Broker) ↔ 📡 EDGE (Gateway) ↔ КУБ devices
```

**Key architectural patterns:**
- **Variable System**: Flexible device adapter architecture in `EDGE/core/device_adapters/` allowing dynamic device configuration
- **Device Registry**: Central device management system tracking multiple CUBE units per EDGE instance
- **Multi-tenant**: Farm-based isolation with role-based access control (ADMIN, FARM_OWNER, VIEWER, EDGE_DEVICE)
- **P2P Tunneling**: IXON-style WebRTC tunnels coordinated by SERVER for direct APP↔EDGE access
- **Dual communication**: Primary P2P tunnels + Tailscale mesh backup

## Common Commands

### Development Setup

```bash
# Install dependencies (choose one)
make install          # Via Poetry (recommended)
make install-pip      # Via pip (fallback)

# First-time setup
make setup           # Creates .env from .env.example, creates dirs

# Environment configuration
cp .env.example .env # Then edit .env with your values
```

### Running Components

```bash
# Run individual components
cd EDGE && python start.py                    # EDGE gateway (all services)
cd EDGE && python start.py --disable-telegram # EDGE without Telegram bot
cd SERVER && python tunnel_broker.py          # SERVER tunnel broker
cd APP && python main_app.py                  # APP backend API

# Or via Makefile
make run-edge        # EDGE with RS485 support
make run-server      # SERVER services
make run-app         # APP web interface

# Service control flags (for EDGE start.py)
--disable-telegram   # Disable Telegram bot
--disable-websocket  # Disable WebSocket server
--disable-mqtt       # Disable MQTT publisher
--disable-edge-ping  # Disable EDGE ping service
--disable-health-api # Disable health monitoring API
--log-level DEBUG    # Set logging level
--offline            # Offline mode (no SERVER communication)
```

### Testing

```bash
# Run tests
make test                           # All tests via pytest
make test-coverage                  # With coverage report

# Component-specific tests
cd EDGE && pytest tests/ -v         # EDGE tests only
cd EDGE && pytest tests/integration/test_edge_offline.py  # Offline mode test

# Pre-commit checks
pre-commit install                  # Install pre-commit hooks
pre-commit run --all-files         # Run all checks manually
```

### Code Quality

```bash
make lint            # Run ruff, black, mypy checks
make format          # Auto-format with black + isort
make clean           # Remove temporary files, caches

# Security checks (via pre-commit)
bandit -r EDGE/ SERVER/ APP/        # Security vulnerability scan
detect-secrets scan                 # Detect hardcoded secrets
```

### Docker Deployment

```bash
# Build and run
make docker          # Build cube-rs:latest image
make docker-run      # Run in container
make docker-compose  # Run all services via compose

# Individual component Docker
cd SERVER && docker-compose up -d   # SERVER services
cd APP && docker build -t cube-rs-app .
```

### Monitoring & Health

```bash
# Health checks
curl http://localhost:8090/health              # EDGE health API
curl http://localhost:8080/health              # SERVER health
curl http://localhost:5000/health              # APP health

# View logs
make logs            # Auto-detect and tail logs
docker logs -f cube-rs                         # Docker logs

# System metrics
curl http://localhost:8090/metrics             # EDGE system metrics
```

## Code Architecture

### EDGE Component (`/EDGE/`)

**Entry Point**: `start.py` - Main launcher orchestrating all EDGE services

**Core Modules** (`core/`):
- `device_registry.py`: Central registry managing multiple CUBE devices with unified Variable System
- `device_adapters/`: Device-specific adapters (kub1063.py, kub1112.py) + base.py + factory.py
- `variable_system.py`: Flexible variable mapping system for dynamic device configuration
- `edge_authentication.py`: API key authentication with SERVER
- `edge_ping_service.py`: Automatic device heartbeat and registration
- `health_checker.py`: System health monitoring with Circuit Breaker pattern
- `error_handler.py`: Centralized error handling with retry logic

**Publishing** (`core/publishing/`):
- `websocket_server.py`: Real-time data streaming (port 8000)
- `mqtt.py`: MQTT publisher for external integrations

**Security** (`core/security/`):
- `mitm_protection.py`: Certificate pinning and MITM attack detection
- `mutual_tls.py`: Mutual TLS authentication for device↔server

**Telegram** (`core/telegram/`):
- `async_bot_main.py`: Async Telegram bot for remote management
- `secure_config.py`: Encrypted token/admin management

**Configuration**:
- `config/app_config.yaml`: Device definitions, Modbus settings, services
- `config/devices.yaml`: Device-specific configurations
- `config/secrets/`: Encrypted secrets (.enc files)

### SERVER Component (`/SERVER/`)

**Core Services**:
- `tunnel_broker.py`: P2P WebRTC tunnel coordinator
- `auth_system.py`: JWT/API key authentication with RBAC
- `admin_cli.py`: CLI for user/device management

**Database**: SQLite (`tunnel_broker.db`) with users, devices, farms, sessions

**Deployment**:
- `docker-compose.yml`: Production-ready stack with Nginx
- `systemd/`: Linux service definitions
- `nginx/`: Reverse proxy configurations

### APP Component (`/APP/`)

**Backend** (`backend/`):
- `app.py`: Main Flask application with CORS
- `api.py`: Extended API routes for mobile clients
- `device_registry.py`: Device management and heartbeat
- `tailscale_integration.py`: Mesh network integration
- `tailscale_manager.py`: Tailscale API client

**Security** (`security/`):
- MITM protection and mutual TLS modules (mirrored from EDGE)

**API Endpoints**:
- `/api/auth/login` - JWT authentication
- `/api/farms` - Farm/device listings
- `/api/devices/{id}/data` - Real-time device data
- `/api/tunnel/connect` - P2P tunnel requests
- `/api/tailscale/*` - Mesh network operations
- `/health` - Health check

## Important Patterns

### Variable System Architecture

The Variable System (`EDGE/core/device_adapters/variable_system.py`) provides:
- Runtime-configurable device variables via YAML
- Type-safe variable definitions (temperature, humidity, bool, enum, etc.)
- Automatic Modbus register mapping
- Device-agnostic data access

**Adding a new device type**:
1. Create adapter in `EDGE/core/device_adapters/{device}.py` inheriting from `BaseDeviceAdapter`
2. Define variables in `config/devices.yaml`
3. Register in `factory.py`

### Authentication Flow

**EDGE ↔ SERVER**:
1. EDGE requests API key from SERVER admin
2. API key stored in `config/secrets/edge_auth.enc`
3. All SERVER requests include `X-API-Key` header
4. JWT tokens for user sessions (short-lived)

**APP ↔ SERVER**:
1. User login via `/api/auth/login`
2. Receive JWT token
3. Include `Authorization: Bearer {token}` in requests

### Device Registry Pattern

Each EDGE instance maintains a DeviceRegistry tracking multiple devices:
- Centralized device lifecycle management
- Heartbeat monitoring
- Error isolation per device
- Unified data publishing

### Security Best Practices

**Secrets Management**:
- Never commit unencrypted secrets
- Use `config/secrets/*.enc` for encrypted storage
- CLI tools: `telegram_secrets_cli.py`, `edge_ping_secrets_cli.py`
- Environment variables override for production: `TELEGRAM_BOT_TOKEN`, `EDGE_API_KEY`

**MITM Protection**:
- Certificate pinning in `core/security/mitm_protection.py`
- Mutual TLS in `core/security/mutual_tls.py`
- Automatic certificate validation

## Configuration Files

**EDGE Configuration** (`config/app_config.yaml`):
```yaml
devices:
  - device_id: "КУБ-1063-001"
    device_type: "КУБ-1063"
    connection:
      type: "modbus_rtu"
      port: "/dev/ttyUSB0"
      baudrate: 9600
      slave_id: 1
```

**Environment Variables** (`.env`):
```bash
# EDGE
EDGE_API_KEY=xxx
EDGE_DEVICE_ID=edge_xxx
TELEGRAM_BOT_TOKEN=xxx
EDGE_OFFLINE_MODE=false

# SERVER
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
JWT_SECRET_KEY=xxx

# APP
SERVER_URL=http://localhost:8080
SECRET_KEY=xxx
DEBUG=false
```

## Testing Strategy

**Unit Tests**: Component-specific logic, mocks for external dependencies
**Integration Tests**: `EDGE/tests/integration/` - cross-component flows
**Load Tests**: `EDGE/tests/load_test.py`, `simple_load_test.py`
**Offline Tests**: `test_edge_offline.py`, `test_telegram_offline.py` - verify autonomous operation

**Pre-commit hooks** run automatically before commits:
- black (formatting)
- ruff (linting)
- mypy (type checking)
- bandit (security)
- detect-secrets (credential leaks)
- Fast unit tests

## Project Structure Context

```
CUBE_RS/
├── EDGE/              # Industrial gateway (autonomous operation)
│   ├── core/          # Core business logic
│   ├── modbus/        # Modbus RTU/TCP implementations
│   ├── config/        # Device configurations
│   ├── tests/         # EDGE-specific tests
│   └── start.py       # Main entry point
├── SERVER/            # Central coordination server
│   ├── tunnel_broker.py
│   ├── auth_system.py
│   └── admin_cli.py
├── APP/               # Mobile/web backend
│   ├── backend/       # Flask API
│   └── main_app.py
├── docs/              # Extended documentation
├── _archive/          # Deprecated/backup code
└── Makefile          # Development commands
```

## Role-Specific Guidance

**As a Senior DevOps/Platform Engineer** (per project instructions):
- Focus on system architecture, performance bottlenecks, scalability
- Use Sequential Thinking for structured analysis
- Prioritize solutions: Critical → Important → Desirable
- Provide concrete code examples, not generalizations
- Evaluate impact vs. effort for changes
- Check IoT-specific patterns: data flow (device → collection → processing → storage → UI)

## Common Development Workflows

### Adding a New Device Type
1. Create `EDGE/core/device_adapters/my_device.py`
2. Implement `BaseDeviceAdapter` interface
3. Define variables in `config/devices.yaml`
4. Register in `device_adapters/factory.py`
5. Add device instance to `config/app_config.yaml`
6. Test with `pytest tests/integration/`

### Debugging Production Issues
1. Check health endpoints: `/health`, `/metrics`
2. Review logs in `logs/` directory
3. Verify configuration: `config/app_config.yaml`
4. Check device connectivity: `EDGE/tools/scan_slave_ids.py`
5. Test Modbus communication: `test_rs485.py`

### Deploying to Production
1. Set environment to production: `ENVIRONMENT=production`
2. Configure secrets in `.env` (never commit!)
3. Build Docker images: `make docker`
4. Deploy with compose: `make docker-compose`
5. Verify health: `make health`
6. Monitor logs: `make logs`

## Additional Resources

- **[README.md](README.md)**: System overview and quick start
- **[ОПИСАНИЕ.md](ОПИСАНИЕ.md)**: Detailed Russian documentation with audit checklist
- **[EDGE/README.md](EDGE/README.md)**: EDGE component documentation
- **[SERVER/README.md](SERVER/README.md)**: SERVER deployment guide
- **[APP/README.md](APP/README.md)**: APP API documentation
- **[docs/](docs/)**: Extended architecture and deployment docs
