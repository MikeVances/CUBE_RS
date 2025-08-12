import socket
import struct
import time

def test_connection():
    """Тест базового подключения"""
    print("🔍 Диагностика Modbus TCP подключения...")
    print("=" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        print("📡 Подключение к tcp.cloudpub.ru:20049...")
        sock.connect(('tcp.cloudpub.ru', 20049))
        print("✅ Подключение установлено")
        
        # Тест 1: Функция 0x03 (чтение holding registers)
        print("\n📤 Тест 1: Функция 0x03 (чтение holding registers)")
        print("-" * 40)
        
        test_addresses = [0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005]
        
        for addr in test_addresses:
            transaction_id = 0x0001
            request = struct.pack('>HHHBBHH',
                transaction_id, 0x0000, 0x0006, 0x01, 0x03, addr, 1
            )
            print(f"📤 Чтение регистра {hex(addr)}...")
            sock.send(request)
            response = sock.recv(1024)
            print(f"📥 Ответ: {response.hex()}")
            
            if len(response) >= 9:
                function_code = response[7]
                if function_code == 0x03:
                    byte_count = response[8]
                    if byte_count >= 2:
                        reg_value = struct.unpack('>H', response[9:11])[0]
                        print(f"   ✅ Значение: 0x{reg_value:04X} ({reg_value})")
                    else:
                        print(f"   ⚠️ Недостаточно данных")
                elif function_code == 0x83:
                    error_code = response[8] if len(response) > 8 else 0
                    print(f"   ❌ Ошибка: код {error_code}")
                else:
                    print(f"   ⚠️ Неожиданный код: 0x{function_code:02X}")
            else:
                print(f"   ❌ Слишком короткий ответ")
            
            time.sleep(0.5)
        
        # Тест 2: Функция 0x04 (чтение input registers)
        print("\n📤 Тест 2: Функция 0x04 (чтение input registers)")
        print("-" * 40)
        
        for addr in test_addresses:
            transaction_id = 0x0002
            request = struct.pack('>HHHBBHH',
                transaction_id, 0x0000, 0x0006, 0x01, 0x04, addr, 1
            )
            print(f"📤 Чтение input регистра {hex(addr)}...")
            sock.send(request)
            response = sock.recv(1024)
            print(f"📥 Ответ: {response.hex()}")
            
            if len(response) >= 9:
                function_code = response[7]
                if function_code == 0x04:
                    byte_count = response[8]
                    if byte_count >= 2:
                        reg_value = struct.unpack('>H', response[9:11])[0]
                        print(f"   ✅ Значение: 0x{reg_value:04X} ({reg_value})")
                    else:
                        print(f"   ⚠️ Недостаточно данных")
                elif function_code == 0x84:
                    error_code = response[8] if len(response) > 8 else 0
                    print(f"   ❌ Ошибка: код {error_code}")
                else:
                    print(f"   ⚠️ Неожиданный код: 0x{function_code:02X}")
            else:
                print(f"   ❌ Слишком короткий ответ")
            
            time.sleep(0.5)
        
        # Тест 3: Попробуем адреса из документации КУБ-1063
        print("\n📤 Тест 3: Адреса из документации КУБ-1063")
        print("-" * 40)
        
        kub_addresses = [0x0301, 0x0083, 0x0084, 0x0085, 0x00D5]
        
        for addr in kub_addresses:
            transaction_id = 0x0003
            request = struct.pack('>HHHBBHH',
                transaction_id, 0x0000, 0x0006, 0x01, 0x04, addr, 1
            )
            print(f"📤 Чтение КУБ регистра {hex(addr)}...")
            sock.send(request)
            response = sock.recv(1024)
            print(f"📥 Ответ: {response.hex()}")
            
            if len(response) >= 9:
                function_code = response[7]
                if function_code == 0x04:
                    byte_count = response[8]
                    if byte_count >= 2:
                        reg_value = struct.unpack('>H', response[9:11])[0]
                        print(f"   ✅ Значение: 0x{reg_value:04X} ({reg_value})")
                    else:
                        print(f"   ⚠️ Недостаточно данных")
                elif function_code == 0x84:
                    error_code = response[8] if len(response) > 8 else 0
                    print(f"   ❌ Ошибка: код {error_code}")
                else:
                    print(f"   ⚠️ Неожиданный код: 0x{function_code:02X}")
            else:
                print(f"   ❌ Слишком короткий ответ")
            
            time.sleep(0.5)
        
        sock.close()
        print("\n✅ Диагностика завершена")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_connection() 