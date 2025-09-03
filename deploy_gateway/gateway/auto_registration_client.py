#!/usr/bin/env python3
"""
Auto Registration Client - Автоматическая регистрация gateway в системе
Клиент для автоматической регистрации устройств с предустановленными ключами
"""

import json
import logging
import os
import platform
import socket
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys
import os

# Добавляем путь к security модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'security'))
from mitm_protection import create_mitm_protected_client

logger = logging.getLogger(__name__)

class HardwareCollector:
    """Сборщик информации о железе для привязки устройства"""
    
    @staticmethod
    def get_mac_addresses() -> list:
        """Получение MAC адресов сетевых интерфейсов"""
        import uuid
        mac_addresses = []
        
        try:
            # Получаем основной MAC адрес
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0,48,8)][::-1])
            if mac != "00:00:00:00:00:00":
                mac_addresses.append(mac)
            
            # Дополнительные MAC адреса из системы
            if platform.system() == "Linux":
                try:
                    result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if 'link/ether' in line:
                            mac = line.split('link/ether')[1].strip().split()[0]
                            if mac not in mac_addresses and mac != "00:00:00:00:00:00":
                                mac_addresses.append(mac)
                except:
                    pass
            elif platform.system() == "Darwin":  # macOS
                try:
                    result = subprocess.run(['ifconfig'], capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if 'ether' in line:
                            parts = line.strip().split()
                            if len(parts) >= 2 and parts[0] == 'ether':
                                mac = parts[1]
                                if mac not in mac_addresses and mac != "00:00:00:00:00:00":
                                    mac_addresses.append(mac)
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"Не удалось получить MAC адреса: {e}")
        
        return mac_addresses[:5]  # Ограничиваем количество

    @staticmethod
    def get_cpu_info() -> str:
        """Получение серийного номера или информации о CPU"""
        try:
            if platform.system() == "Linux":
                # Попробуем получить серийный номер из /proc/cpuinfo
                try:
                    with open('/proc/cpuinfo', 'r') as f:
                        for line in f:
                            if 'serial' in line.lower():
                                return line.split(':')[1].strip()
                except:
                    pass
                
                # Или из dmidecode
                try:
                    result = subprocess.run(['dmidecode', '-s', 'processor-serial-number'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except:
                    pass
            
            elif platform.system() == "Darwin":  # macOS
                try:
                    result = subprocess.run(['system_profiler', 'SPHardwareDataType'], 
                                          capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if 'Serial Number' in line:
                            return line.split(':')[1].strip()
                except:
                    pass
            
            # Fallback - используем информацию о процессоре
            return f"{platform.processor()}_{platform.machine()}"
            
        except Exception as e:
            logger.warning(f"Не удалось получить информацию о CPU: {e}")
            return f"unknown_cpu_{int(time.time())}"

    @staticmethod
    def get_disk_info() -> str:
        """Получение серийного номера диска"""
        try:
            if platform.system() == "Linux":
                # Пробуем получить серийный номер основного диска
                try:
                    result = subprocess.run(['lsblk', '-o', 'NAME,SERIAL', '-n'], 
                                          capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        parts = line.strip().split()
                        if len(parts) >= 2 and not parts[0].startswith('├') and not parts[0].startswith('└'):
                            serial = ' '.join(parts[1:]).strip()
                            if serial and serial != '':
                                return serial
                except:
                    pass
                
            elif platform.system() == "Darwin":  # macOS
                try:
                    result = subprocess.run(['system_profiler', 'SPStorageDataType'], 
                                          capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if 'Serial Number' in line:
                            return line.split(':')[1].strip()
                except:
                    pass
                    
            # Fallback
            return f"unknown_disk_{platform.node()}"
            
        except Exception as e:
            logger.warning(f"Не удалось получить информацию о диске: {e}")
            return f"unknown_disk_{int(time.time())}"

    @staticmethod 
    def get_board_info() -> str:
        """Получение информации о материнской плате"""
        try:
            if platform.system() == "Linux":
                try:
                    result = subprocess.run(['dmidecode', '-s', 'baseboard-serial-number'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except:
                    pass
                    
            elif platform.system() == "Darwin":  # macOS
                try:
                    result = subprocess.run(['ioreg', '-l'], capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if 'IOPlatformSerialNumber' in line:
                            return line.split('"')[3] if '"' in line else line.split('=')[1].strip()
                except:
                    pass
                    
            # Fallback
            return f"unknown_board_{platform.node()}"
            
        except Exception as e:
            logger.warning(f"Не удалось получить информацию о плате: {e}")
            return f"unknown_board_{int(time.time())}"

    @classmethod
    def collect_hardware_signature(cls) -> Dict[str, Any]:
        """Сбор полной подписи железа"""
        return {
            "mac_addresses": cls.get_mac_addresses(),
            "cpu_serial": cls.get_cpu_info(),
            "disk_serial": cls.get_disk_info(),
            "board_serial": cls.get_board_info(),
            "hostname": platform.node(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor()
            },
            "collected_at": datetime.now().isoformat()
        }

class AutoRegistrationClient:
    """Клиент автоматической регистрации gateway"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "/etc/cube_gateway/registration.conf"
        self.config = self.load_config()
        self.setup_requests_session()
        
        # Настройка логирования
        self.setup_logging()
    
    def setup_logging(self):
        """Настройка логирования"""
        log_level = self.config.get('log_level', 'INFO')
        log_file = self.config.get('log_file', '/var/log/cube_gateway/registration.log')
        
        # Создаем директорию для логов если её нет
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации регистрации"""
        default_config = {
            "server_url": "http://localhost:8000",  # URL центрального сервера
            "auth_key": "",  # Предустановленный auth key
            "activation_token": "",  # Токен активации (если есть)
            "device_type": "gateway",
            "registration_endpoint": "/api/v1/device-registry/register",
            "activation_endpoint": "/api/v1/device-registry/activate", 
            "retry_attempts": 5,
            "retry_delay": 60,  # секунды
            "registration_timeout": 30,  # секунды
            "log_level": "INFO",
            "log_file": "/var/log/cube_gateway/registration.log",
            "status_file": "/var/lib/cube_gateway/registration_status.json",
            "auto_retry": True,
            "verify_ssl": True
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    default_config.update(file_config)
            else:
                # Создаем конфиг файл с дефолтными настройками
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                logger.info(f"Создан конфиг файл: {self.config_path}")
                
        except Exception as e:
            logger.warning(f"Ошибка загрузки конфига: {e}, используем дефолтный")
        
        return default_config
    
    def setup_requests_session(self):
        """Настройка HTTP сессии с повторами и MITM защитой"""
        # Используем защищенный от MITM клиент
        server_url = self.config.get('server_url', 'http://localhost:8000')
        
        try:
            # Создаем защищенный клиент с certificate pinning
            protected_client = create_mitm_protected_client(server_url)
            self.session = protected_client.session
            logger.info("Инициализирован защищенный от MITM HTTP клиент")
            
        except Exception as e:
            logger.warning(f"Не удалось создать защищенный клиент, используем стандартный: {e}")
            # Fallback к стандартному клиенту
            self.session = requests.Session()
            
            # Настройка повторов
            retry_strategy = Retry(
                total=self.config.get('retry_attempts', 5),
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        
        # Настройка таймаутов
        self.session.timeout = self.config.get('registration_timeout', 30)
        
        # Настройка SSL
        self.session.verify = self.config.get('verify_ssl', True)
    
    def get_registration_status(self) -> Dict[str, Any]:
        """Получение статуса регистрации из файла"""
        status_file = self.config.get('status_file', '/var/lib/cube_gateway/registration_status.json')
        
        try:
            if os.path.exists(status_file):
                with open(status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка чтения статуса регистрации: {e}")
        
        return {"status": "not_registered", "device_id": None}
    
    def save_registration_status(self, status: Dict[str, Any]):
        """Сохранение статуса регистрации в файл"""
        status_file = self.config.get('status_file', '/var/lib/cube_gateway/registration_status.json')
        
        try:
            os.makedirs(os.path.dirname(status_file), exist_ok=True)
            status["updated_at"] = datetime.now().isoformat()
            
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения статуса регистрации: {e}")
    
    def activate_device(self) -> bool:
        """Активация устройства в поле (если есть activation_token)"""
        activation_token = self.config.get('activation_token')
        if not activation_token:
            logger.info("Токен активации не настроен, пропускаем активацию")
            return True
        
        try:
            # Собираем подпись железа
            hardware_signature = HardwareCollector.collect_hardware_signature()
            
            # Данные для активации
            activation_data = {
                "activation_token": activation_token,
                "hardware_signature": hardware_signature,
                "installer_id": f"auto_client_{platform.node()}"
            }
            
            # Отправляем запрос активации
            url = f"{self.config['server_url']}{self.config['activation_endpoint']}"
            
            logger.info(f"Отправка запроса активации на {url}")
            response = self.session.post(url, json=activation_data)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Устройство активировано: {result.get('device_serial')}")
                logger.info(f"Registration request ID: {result.get('registration_request_id')}")
                
                # Сохраняем статус активации
                self.save_registration_status({
                    "status": "activated",
                    "device_serial": result.get('device_serial'),
                    "registration_request_id": result.get('registration_request_id'),
                    "next_step": "pending_approval"
                })
                
                return True
            else:
                logger.error(f"Ошибка активации: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Критическая ошибка активации: {e}")
            return False
    
    def register_device(self) -> bool:
        """Регистрация устройства в системе"""
        auth_key = self.config.get('auth_key')
        if not auth_key:
            logger.error("Auth key не настроен в конфигурации")
            return False
        
        try:
            # Собираем информацию об устройстве
            device_info = {
                "hostname": platform.node(),
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor()
                },
                "network": {
                    "hostname": socket.gethostname(),
                    "fqdn": socket.getfqdn()
                },
                "registration_client": {
                    "version": "1.0.0",
                    "method": "auto_registration",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Добавляем подпись железа
            device_info["hardware_signature"] = HardwareCollector.collect_hardware_signature()
            
            # Данные для регистрации
            registration_data = {
                "auth_key": auth_key,
                "device_hostname": platform.node(),
                "device_type": self.config.get('device_type', 'gateway'),
                "device_info": device_info
            }
            
            # Отправляем запрос регистрации
            url = f"{self.config['server_url']}{self.config['registration_endpoint']}"
            
            logger.info(f"Отправка запроса регистрации на {url}")
            response = self.session.post(url, json=registration_data)
            
            if response.status_code == 201:
                result = response.json()
                request_id = result.get('request_id')
                
                logger.info(f"Запрос на регистрацию создан: {request_id}")
                logger.info("Ожидание одобрения администратором...")
                
                # Сохраняем статус регистрации
                self.save_registration_status({
                    "status": "pending_approval",
                    "request_id": request_id,
                    "device_hostname": registration_data['device_hostname'],
                    "device_type": registration_data['device_type']
                })
                
                return True
            else:
                logger.error(f"Ошибка регистрации: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Критическая ошибка регистрации: {e}")
            return False
    
    def check_registration_approval(self, request_id: str) -> Optional[str]:
        """Проверка одобрения регистрации"""
        try:
            url = f"{self.config['server_url']}/api/v1/device-registry/status/{request_id}"
            
            response = self.session.get(url)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                
                if status == 'approved':
                    device_id = result.get('device_id')
                    logger.info(f"Регистрация одобрена! Device ID: {device_id}")
                    
                    # Обновляем статус
                    self.save_registration_status({
                        "status": "registered",
                        "device_id": device_id,
                        "approved_at": datetime.now().isoformat()
                    })
                    
                    return device_id
                elif status == 'rejected':
                    reason = result.get('reason', 'Не указана')
                    logger.error(f"Регистрация отклонена: {reason}")
                    
                    self.save_registration_status({
                        "status": "rejected",
                        "reason": reason
                    })
                    
                    return None
                else:
                    logger.info(f"Статус регистрации: {status}")
                    return None
            else:
                logger.warning(f"Не удалось проверить статус: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка проверки статуса регистрации: {e}")
            return None
    
    def run_registration_cycle(self) -> bool:
        """Выполнение полного цикла регистрации"""
        logger.info("Запуск цикла автоматической регистрации")
        
        # Проверяем текущий статус
        current_status = self.get_registration_status()
        logger.info(f"Текущий статус: {current_status.get('status')}")
        
        if current_status.get('status') == 'registered':
            logger.info(f"Устройство уже зарегистрировано с ID: {current_status.get('device_id')}")
            return True
        
        # Если есть токен активации, сначала активируем
        if self.config.get('activation_token') and current_status.get('status') != 'activated':
            logger.info("Выполнение активации устройства...")
            if not self.activate_device():
                logger.error("Активация не удалась")
                return False
            
            # Обновляем статус после активации
            current_status = self.get_registration_status()
        
        # Если статус pending_approval, проверяем одобрение
        if current_status.get('status') == 'pending_approval':
            request_id = current_status.get('request_id')
            if request_id:
                logger.info("Проверка статуса одобрения...")
                device_id = self.check_registration_approval(request_id)
                if device_id:
                    return True
        
        # Если нет pending запроса или активации, создаем новый
        if current_status.get('status') in ['not_registered', 'rejected']:
            logger.info("Создание нового запроса регистрации...")
            if not self.register_device():
                return False
        
        # Ждем одобрения с повторными проверками
        if self.config.get('auto_retry', True):
            request_id = self.get_registration_status().get('request_id')
            if request_id:
                logger.info("Ожидание одобрения администратором...")
                
                max_attempts = self.config.get('retry_attempts', 5)
                retry_delay = self.config.get('retry_delay', 60)
                
                for attempt in range(max_attempts):
                    time.sleep(retry_delay)
                    logger.info(f"Проверка одобрения (попытка {attempt + 1}/{max_attempts})...")
                    
                    device_id = self.check_registration_approval(request_id)
                    if device_id:
                        return True
                    
                logger.warning("Превышено максимальное количество попыток проверки одобрения")
        
        return False
    
    def start_daemon(self):
        """Запуск в режиме демона с периодическими проверками"""
        logger.info("Запуск демона автоматической регистрации")
        
        while True:
            try:
                if self.run_registration_cycle():
                    logger.info("Регистрация завершена успешно")
                    # В продакшене можно добавить периодические проверки связи
                    # Для демонстрации выходим после успешной регистрации
                    break
                else:
                    logger.warning("Цикл регистрации не завершен, повтор через час")
                    time.sleep(3600)  # Ждем час перед повтором
                    
            except KeyboardInterrupt:
                logger.info("Получен сигнал завершения")
                break
            except Exception as e:
                logger.error(f"Критическая ошибка в демоне: {e}")
                time.sleep(300)  # Ждем 5 минут перед повтором

def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto Registration Client для CUBE_RS Gateway")
    parser.add_argument('--config', help='Путь к конфигурационному файлу')
    parser.add_argument('--daemon', action='store_true', help='Запуск в режиме демона')
    parser.add_argument('--once', action='store_true', help='Однократный запуск регистрации')
    parser.add_argument('--status', action='store_true', help='Показать текущий статус')
    parser.add_argument('--test-hardware', action='store_true', help='Тест сбора информации о железе')
    
    args = parser.parse_args()
    
    if args.test_hardware:
        print("🔧 Тест сбора информации о железе:")
        hw_info = HardwareCollector.collect_hardware_signature()
        print(json.dumps(hw_info, indent=2, ensure_ascii=False))
        return
    
    client = AutoRegistrationClient(args.config)
    
    if args.status:
        status = client.get_registration_status()
        print(f"📊 Статус регистрации: {status.get('status')}")
        if status.get('device_id'):
            print(f"   Device ID: {status['device_id']}")
        if status.get('request_id'):
            print(f"   Request ID: {status['request_id']}")
        if status.get('updated_at'):
            print(f"   Обновлено: {status['updated_at']}")
        return
    
    if args.daemon:
        client.start_daemon()
    else:
        # Однократный запуск (по умолчанию)
        success = client.run_registration_cycle()
        if success:
            print("✅ Регистрация завершена успешно")
        else:
            print("❌ Регистрация не завершена")
            exit(1)

if __name__ == "__main__":
    main()