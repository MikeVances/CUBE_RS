#!/usr/bin/env python3
"""
Start only TypedModbusGateway - the modern, reliable gateway.
"""
import asyncio
import logging
import signal

from core.config_manager import get_config

from modbus.gateway_typed import TypedModbusGateway

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point."""
    logger.info("🚀 Starting CUBE_RS TypedModbusGateway...")

    # Load configuration
    config = get_config()

    # Create gateway with config-based port
    gateway = TypedModbusGateway(
        host="0.0.0.0",  # Listen on all interfaces
        port=getattr(config.modbus_tcp, 'port', 5020),  # Use configured port or default
        db_path="kub_data.db",
        max_concurrent_requests=100,
    )

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start server
        await gateway.start_server()

        logger.info(f"✅ Gateway is running on http://0.0.0.0:{gateway.port}")
        logger.info("🔗 Available endpoints:")
        logger.info(f"  • Health: http://0.0.0.0:{gateway.port}/health")
        logger.info(f"  • Metrics: http://0.0.0.0:{gateway.port}/metrics")
        logger.info(f"  • Modbus Read: POST http://0.0.0.0:{gateway.port}/modbus/read")
        logger.info(f"  • Modbus Write: POST http://0.0.0.0:{gateway.port}/modbus/write")
        logger.info("Press Ctrl+C to stop")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except KeyboardInterrupt:
        logger.info("👋 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Gateway failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("🛑 Stopping gateway...")
        await gateway.stop_server()
        logger.info("✅ Gateway stopped gracefully")


if __name__ == "__main__":
    asyncio.run(main())
