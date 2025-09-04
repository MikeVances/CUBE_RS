#!/usr/bin/env python3
"""
Test script for CUBE-1063 controller via USB/Modbus RTU
"""

import asyncio
import logging
from datetime import datetime

from core.types import ModbusRequest, ModbusFunctionCode, ModbusDevice, ModbusConnectionInfo, ModbusConnectionType
from modbus.async_client import AsyncModbusClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_cube1063():
    """Test connection and data reading from CUBE-1063"""
    
    # Create async Modbus client
    client = AsyncModbusClient(max_concurrent_requests=5)
    
    # CUBE-1063 device configuration
    cube_device = ModbusDevice(
        device_id=1,  # Standard slave address for CUBE-1063
        name="CUBE-1063 Controller",
        connection_info=ModbusConnectionInfo(
            connection_type=ModbusConnectionType.RTU,
            host="/dev/tty.usbserial-21230",  # USB serial port
            port=9600,  # Baud rate (using port field for baud rate in RTU)
            device_address=1,  # Modbus slave address
            timeout=2.0,
            retry_count=3
        ),
        description="CUBE-1063 Industrial Controller via USB"
    )
    
    print(f"🔧 Testing CUBE-1063 controller...")
    print(f"📡 Port: {cube_device.connection_info.host}")
    print(f"📊 Baud Rate: {cube_device.connection_info.port}")
    print(f"🎯 Device Address: {cube_device.connection_info.device_address}")
    print("-" * 50)
    
    try:
        # Register device
        client.register_device(cube_device)
        print(f"✅ Device registered: {cube_device.name}")
        
        # Test 1: Read Input Registers (typical for sensors)
        print(f"\n📖 Test 1: Reading Input Registers (0-9)")
        request1 = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_INPUT_REGISTERS,
            register_address=0,
            register_count=10
        )
        
        response1 = await client.execute_request(request1)
        print(f"Response: {response1.success}")
        if response1.success:
            print(f"📈 Data: {response1.data}")
            print(f"⏱️  Response Time: {response1.response_time_ms:.2f} ms")
        else:
            print(f"❌ Error: {response1.error_message}")
        
        # Test 2: Read Holding Registers  
        print(f"\n📖 Test 2: Reading Holding Registers (0-9)")
        request2 = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=10
        )
        
        response2 = await client.execute_request(request2)
        print(f"Response: {response2.success}")
        if response2.success:
            print(f"📈 Data: {response2.data}")
            print(f"⏱️  Response Time: {response2.response_time_ms:.2f} ms")
        else:
            print(f"❌ Error: {response2.error_message}")
        
        # Test 3: Read Coils (if available)
        print(f"\n📖 Test 3: Reading Coils (0-15)")
        request3 = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_COILS,
            register_address=0,
            register_count=16
        )
        
        response3 = await client.execute_request(request3)
        print(f"Response: {response3.success}")
        if response3.success:
            print(f"📈 Data: {response3.data}")
            print(f"⏱️  Response Time: {response3.response_time_ms:.2f} ms")
        else:
            print(f"❌ Error: {response3.error_message}")
        
        # Test 4: Try different register ranges for typical CUBE-1063 data
        print(f"\n📖 Test 4: Reading CUBE-1063 specific registers (40001-40010)")
        request4 = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=40001,  # CUBE-1063 specific range
            register_count=10
        )
        
        response4 = await client.execute_request(request4)
        print(f"Response: {response4.success}")
        if response4.success:
            print(f"📈 Data: {response4.data}")
            print(f"⏱️  Response Time: {response4.response_time_ms:.2f} ms")
        else:
            print(f"❌ Error: {response4.error_message}")
        
        # Display device statistics
        device = client.get_device(1)
        if device:
            print(f"\n📊 Device Statistics:")
            print(f"   Total Requests: {device.total_requests}")
            print(f"   Successful Requests: {device.successful_requests}")  
            print(f"   Success Rate: {device.success_rate:.1f}%")
            print(f"   Status: {device.status.name}")
            if device.last_success:
                print(f"   Last Success: {device.last_success.strftime('%Y-%m-%d %H:%M:%S')}")
            if device.last_error:
                print(f"   Last Error: {device.last_error}")
    
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"💥 Test failed: {e}")
    
    finally:
        # Cleanup
        print(f"\n🧹 Cleaning up...")
        await asyncio.sleep(0.5)  # Brief delay for cleanup

if __name__ == "__main__":
    print("🚀 Starting CUBE-1063 Test...")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    try:
        asyncio.run(test_cube1063())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
    
    print("=" * 50)
    print("🏁 Test completed!")