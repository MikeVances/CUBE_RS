#!/usr/bin/env python3
"""
Certificate Manager CLI - Управление сертификатами для MITM защиты
CLI утилита для создания, управления и мониторинга сертификатов
"""

import argparse
import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Добавляем путь к security модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'security'))

from mutual_tls import CertificateAuthority, setup_device_mtls
from mitm_protection import CertificateManager, get_server_certificate_der
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import socket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_ca(args):
    """Инициализация центра сертификации"""
    try:
        print("🏛️ Инициализация центра сертификации...")
        
        ca_config = {
            "ca_name": args.ca_name or "CUBE_RS_CA",
            "ca_country": args.country or "RU",
            "ca_state": args.state or "Moscow",
            "ca_locality": args.locality or "Moscow",
            "ca_organization": args.organization or "CUBE_RS",
            "ca_organizational_unit": args.organizational_unit or "Security",
            "ca_common_name": args.common_name or "CUBE_RS Root CA",
            "ca_validity_days": args.validity_days or 3650,
            "key_size": args.key_size or 2048,
            "ca_cert_path": args.ca_cert_path or "/etc/cube_gateway/certs/ca.crt",
            "ca_key_path": args.ca_key_path or "/etc/cube_gateway/certs/ca.key",
            "client_certs_dir": args.client_certs_dir or "/etc/cube_gateway/certs/clients/",
            "auto_generate_ca": True
        }
        
        # Сохраняем конфигурацию
        config_path = args.config_path or "/etc/cube_gateway/ca_config.json"
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(ca_config, f, indent=2, ensure_ascii=False)
        
        # Создаем CA
        ca = CertificateAuthority(config_path)
        
        print("✅ Центр сертификации инициализирован:")
        print(f"   CA сертификат: {ca_config['ca_cert_path']}")
        print(f"   CA ключ: {ca_config['ca_key_path']}")
        print(f"   Конфигурация: {config_path}")
        print(f"   Действителен до: {ca.ca_cert.not_valid_after}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации CA: {e}")
        return False

def create_client_cert(args):
    """Создание клиентского сертификата"""
    try:
        print(f"📜 Создание клиентского сертификата для {args.device_id}...")
        
        ca = CertificateAuthority(args.ca_config)
        
        # Подготавливаем параметры
        dns_names = args.dns_names.split(',') if args.dns_names else []
        ip_addresses = args.ip_addresses.split(',') if args.ip_addresses else []
        
        # Создаем сертификат
        cert_pem, key_pem = ca.create_client_certificate(
            device_id=args.device_id,
            common_name=args.common_name,
            dns_names=dns_names,
            ip_addresses=ip_addresses,
            validity_days=args.validity_days
        )
        
        if args.save:
            # Сохраняем в файлы
            cert_path, key_path = ca.save_client_certificate(args.device_id, cert_pem, key_pem)
            print(f"✅ Клиентский сертификат создан:")
            print(f"   Сертификат: {cert_path}")
            print(f"   Ключ: {key_path}")
        else:
            # Выводим на экран
            print("✅ Клиентский сертификат:")
            print("--- CERTIFICATE ---")
            print(cert_pem.decode('utf-8'))
            print("--- PRIVATE KEY ---")
            print(key_pem.decode('utf-8'))
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания клиентского сертификата: {e}")
        return False

def list_certificates(args):
    """Список клиентских сертификатов"""
    try:
        ca = CertificateAuthority(args.ca_config)
        clients_dir = ca.config['client_certs_dir']
        
        if not os.path.exists(clients_dir):
            print("📂 Клиентских сертификатов не найдено")
            return True
        
        cert_files = list(Path(clients_dir).glob("*.crt"))
        
        if not cert_files:
            print("📂 Клиентских сертификатов не найдено")
            return True
        
        print(f"📜 Клиентские сертификаты ({len(cert_files)}):")
        print()
        
        for cert_file in sorted(cert_files):
            try:
                with open(cert_file, 'rb') as f:
                    cert = x509.load_pem_x509_certificate(f.read(), default_backend())
                
                device_id = cert_file.stem
                common_name = dict(x[0] for x in cert.subject)['commonName']
                expires = cert.not_valid_after
                days_left = (expires - datetime.now()).days
                
                status = "✅" if days_left > 30 else "⚠️" if days_left > 0 else "❌"
                
                print(f"{status} {device_id}")
                print(f"   CN: {common_name}")
                print(f"   Истекает: {expires.strftime('%Y-%m-%d %H:%M:%S')} ({days_left} дней)")
                print(f"   Файл: {cert_file}")
                
                # SAN информация
                try:
                    san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    san_names = []
                    for name in san_ext.value:
                        if isinstance(name, x509.DNSName):
                            san_names.append(f"DNS:{name.value}")
                        elif isinstance(name, x509.IPAddress):
                            san_names.append(f"IP:{name.value}")
                    
                    if san_names:
                        print(f"   SAN: {', '.join(san_names)}")
                except:
                    pass
                
                print()
                
            except Exception as e:
                print(f"❌ Ошибка чтения {cert_file}: {e}")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения списка сертификатов: {e}")
        return False

def revoke_certificate(args):
    """Отзыв сертификата"""
    try:
        ca = CertificateAuthority(args.ca_config)
        clients_dir = ca.config['client_certs_dir']
        
        cert_path = os.path.join(clients_dir, f"{args.device_id}.crt")
        key_path = os.path.join(clients_dir, f"{args.device_id}.key")
        
        if not os.path.exists(cert_path):
            print(f"❌ Сертификат для {args.device_id} не найден")
            return False
        
        # Перемещаем в папку отозванных
        revoked_dir = os.path.join(clients_dir, "revoked")
        os.makedirs(revoked_dir, exist_ok=True)
        
        revoked_cert_path = os.path.join(revoked_dir, f"{args.device_id}.crt")
        revoked_key_path = os.path.join(revoked_dir, f"{args.device_id}.key")
        
        os.rename(cert_path, revoked_cert_path)
        if os.path.exists(key_path):
            os.rename(key_path, revoked_key_path)
        
        print(f"✅ Сертификат {args.device_id} отозван:")
        print(f"   Перемещен в: {revoked_cert_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка отзыва сертификата: {e}")
        return False

def pin_certificate(args):
    """Закрепление сертификата для защиты от MITM"""
    try:
        print(f"🔒 Закрепление сертификата для {args.hostname}...")
        
        cert_manager = CertificateManager(args.pins_config)
        
        if args.cert_file:
            # Загружаем из файла
            with open(args.cert_file, 'rb') as f:
                cert_data = f.read()
                
            # Определяем формат (PEM или DER)
            if cert_data.startswith(b'-----BEGIN CERTIFICATE-----'):
                cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                cert_der = cert.public_bytes(x509.Encoding.DER)
            else:
                cert_der = cert_data
        else:
            # Получаем сертификат с сервера
            port = args.port or 443
            print(f"   Получение сертификата с {args.hostname}:{port}...")
            cert_der = get_server_certificate_der(args.hostname, port)
            
            if not cert_der:
                print(f"❌ Не удалось получить сертификат с {args.hostname}:{port}")
                return False
        
        # Добавляем pin
        pin_type = args.pin_type or "pubkey-sha256"
        description = args.description or f"Certificate pin for {args.hostname}"
        
        cert_manager.add_certificate_pin(
            hostname=args.hostname,
            cert_der=cert_der,
            pin_type=pin_type,
            description=description
        )
        
        print(f"✅ Сертификат закреплен для {args.hostname}")
        print(f"   Тип pin: {pin_type}")
        print(f"   Конфиг: {cert_manager.config_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка закрепления сертификата: {e}")
        return False

def list_pins(args):
    """Список закрепленных сертификатов"""
    try:
        cert_manager = CertificateManager(args.pins_config)
        
        if not cert_manager.pins_cache:
            print("🔒 Закрепленных сертификатов не найдено")
            return True
        
        print(f"🔒 Закрепленные сертификаты ({len(cert_manager.pins_cache)}):")
        print()
        
        for hostname, pin_info in cert_manager.pins_cache.items():
            print(f"🌐 {hostname}")
            print(f"   Тип pin: {pin_info.pin_type}")
            print(f"   Pin: {pin_info.pin_value[:40]}...")
            print(f"   Описание: {pin_info.description}")
            print(f"   Создан: {pin_info.created_at}")
            
            if pin_info.expires:
                expires_date = datetime.fromisoformat(pin_info.expires)
                days_left = (expires_date - datetime.now()).days
                print(f"   Истекает: {pin_info.expires} ({days_left} дней)")
            
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения списка pins: {e}")
        return False

def verify_pin(args):
    """Проверка certificate pin"""
    try:
        print(f"🔍 Проверка certificate pin для {args.hostname}...")
        
        cert_manager = CertificateManager(args.pins_config)
        port = args.port or 443
        
        # Получаем текущий сертификат
        cert_der = get_server_certificate_der(args.hostname, port)
        if not cert_der:
            print(f"❌ Не удалось получить сертификат с {args.hostname}:{port}")
            return False
        
        # Проверяем pin
        is_valid = cert_manager.verify_certificate_pin(args.hostname, cert_der)
        
        if is_valid:
            print(f"✅ Certificate pin для {args.hostname} ПОДТВЕРЖДЕН")
        else:
            print(f"❌ Certificate pin для {args.hostname} НЕ СОВПАДАЕТ!")
            print("   Возможна MITM атака или сертификат был обновлен")
        
        return is_valid
        
    except Exception as e:
        print(f"❌ Ошибка проверки pin: {e}")
        return False

def ca_info(args):
    """Информация о центре сертификации"""
    try:
        ca = CertificateAuthority(args.ca_config)
        
        if not ca.ca_cert:
            print("❌ CA не инициализирован")
            return False
        
        print("🏛️ Информация о центре сертификации:")
        print()
        
        # Основная информация
        subject_dict = dict(x[0] for x in ca.ca_cert.subject)
        print(f"Название: {subject_dict.get('commonName', 'N/A')}")
        print(f"Организация: {subject_dict.get('organizationName', 'N/A')}")
        print(f"Страна: {subject_dict.get('countryName', 'N/A')}")
        print(f"Серийный номер: {ca.ca_cert.serial_number}")
        print()
        
        # Сроки действия
        not_before = ca.ca_cert.not_valid_before
        not_after = ca.ca_cert.not_valid_after
        days_left = (not_after - datetime.now()).days
        
        print(f"Действителен с: {not_before.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Действителен до: {not_after.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Осталось дней: {days_left}")
        
        if days_left < 30:
            print("⚠️  CA сертификат скоро истечет!")
        elif days_left < 0:
            print("❌ CA сертификат истек!")
        
        print()
        
        # Файлы
        print(f"CA сертификат: {ca.config['ca_cert_path']}")
        print(f"CA ключ: {ca.config['ca_key_path']}")
        print(f"Клиентские сертификаты: {ca.config['client_certs_dir']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения информации о CA: {e}")
        return False

def main():
    """Главная функция CLI"""
    parser = argparse.ArgumentParser(
        description="Certificate Manager CLI - Управление сертификатами CUBE_RS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Инициализация CA
  python certificate_manager_cli.py init-ca --ca-name "CUBE_RS_CA" --organization "My Company"

  # Создание клиентского сертификата
  python certificate_manager_cli.py create-client --device-id gateway-001 --save

  # Список клиентских сертификатов
  python certificate_manager_cli.py list-certs

  # Закрепление сертификата сервера
  python certificate_manager_cli.py pin-cert --hostname api.example.com

  # Проверка certificate pin
  python certificate_manager_cli.py verify-pin --hostname api.example.com

  # Информация о CA
  python certificate_manager_cli.py ca-info
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')
    
    # Инициализация CA
    init_parser = subparsers.add_parser('init-ca', help='Инициализация центра сертификации')
    init_parser.add_argument('--ca-name', help='Название CA')
    init_parser.add_argument('--country', help='Код страны (RU)')
    init_parser.add_argument('--state', help='Регион/область')
    init_parser.add_argument('--locality', help='Город')
    init_parser.add_argument('--organization', help='Организация')
    init_parser.add_argument('--organizational-unit', help='Подразделение')
    init_parser.add_argument('--common-name', help='Common Name CA')
    init_parser.add_argument('--validity-days', type=int, help='Срок действия CA в днях (default: 3650)')
    init_parser.add_argument('--key-size', type=int, help='Размер ключа (default: 2048)')
    init_parser.add_argument('--ca-cert-path', help='Путь к сертификату CA')
    init_parser.add_argument('--ca-key-path', help='Путь к ключу CA')
    init_parser.add_argument('--client-certs-dir', help='Директория клиентских сертификатов')
    init_parser.add_argument('--config-path', help='Путь к конфигурации CA')
    init_parser.set_defaults(func=init_ca)
    
    # Создание клиентского сертификата
    client_parser = subparsers.add_parser('create-client', help='Создание клиентского сертификата')
    client_parser.add_argument('--device-id', required=True, help='ID устройства')
    client_parser.add_argument('--common-name', help='Common Name для сертификата')
    client_parser.add_argument('--dns-names', help='DNS имена через запятую')
    client_parser.add_argument('--ip-addresses', help='IP адреса через запятую')
    client_parser.add_argument('--validity-days', type=int, default=365, help='Срок действия в днях')
    client_parser.add_argument('--save', action='store_true', help='Сохранить в файлы')
    client_parser.add_argument('--ca-config', help='Путь к конфигурации CA')
    client_parser.set_defaults(func=create_client_cert)
    
    # Список сертификатов
    list_parser = subparsers.add_parser('list-certs', help='Список клиентских сертификатов')
    list_parser.add_argument('--ca-config', help='Путь к конфигурации CA')
    list_parser.set_defaults(func=list_certificates)
    
    # Отзыв сертификата
    revoke_parser = subparsers.add_parser('revoke-cert', help='Отзыв сертификата')
    revoke_parser.add_argument('--device-id', required=True, help='ID устройства')
    revoke_parser.add_argument('--ca-config', help='Путь к конфигурации CA')
    revoke_parser.set_defaults(func=revoke_certificate)
    
    # Закрепление сертификата
    pin_parser = subparsers.add_parser('pin-cert', help='Закрепление сертификата для MITM защиты')
    pin_parser.add_argument('--hostname', required=True, help='Имя хоста')
    pin_parser.add_argument('--port', type=int, help='Порт (default: 443)')
    pin_parser.add_argument('--cert-file', help='Путь к файлу сертификата')
    pin_parser.add_argument('--pin-type', default='pubkey-sha256', help='Тип pin (default: pubkey-sha256)')
    pin_parser.add_argument('--description', help='Описание pin')
    pin_parser.add_argument('--pins-config', help='Путь к конфигурации pins')
    pin_parser.set_defaults(func=pin_certificate)
    
    # Список pins
    pins_parser = subparsers.add_parser('list-pins', help='Список закрепленных сертификатов')
    pins_parser.add_argument('--pins-config', help='Путь к конфигурации pins')
    pins_parser.set_defaults(func=list_pins)
    
    # Проверка pin
    verify_parser = subparsers.add_parser('verify-pin', help='Проверка certificate pin')
    verify_parser.add_argument('--hostname', required=True, help='Имя хоста')
    verify_parser.add_argument('--port', type=int, help='Порт (default: 443)')
    verify_parser.add_argument('--pins-config', help='Путь к конфигурации pins')
    verify_parser.set_defaults(func=verify_pin)
    
    # Информация о CA
    info_parser = subparsers.add_parser('ca-info', help='Информация о центре сертификации')
    info_parser.add_argument('--ca-config', help='Путь к конфигурации CA')
    info_parser.set_defaults(func=ca_info)
    
    # Парсим аргументы
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return False
    
    # Выполняем команду
    try:
        return args.func(args)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.exception("Критическая ошибка в certificate_manager_cli")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)