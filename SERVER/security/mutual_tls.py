#!/usr/bin/env python3
"""
Mutual TLS Authentication - Взаимная TLS аутентификация
Создание и управление клиентскими сертификатами для mTLS
"""

import ipaddress
import json
import logging
import os
import socket
import ssl
from datetime import datetime, timedelta
from typing import Any

import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

logger = logging.getLogger(__name__)


class CertificateAuthority:
    """Центр сертификации для создания клиентских сертификатов"""

    def __init__(self, ca_config_path: str = None):
        self.config_path = ca_config_path or "/etc/cube_gateway/ca_config.json"
        self.ca_cert = None
        self.ca_private_key = None
        self.config = self.load_ca_config()

        # Инициализируем CA или загружаем существующий
        self.load_or_create_ca()

    def load_ca_config(self) -> dict[str, Any]:
        """Загрузка конфигурации CA"""
        default_config = {
            "ca_name": "CUBE_RS_CA",
            "ca_country": "RU",
            "ca_state": "Moscow",
            "ca_locality": "Moscow",
            "ca_organization": "CUBE_RS",
            "ca_organizational_unit": "Security",
            "ca_common_name": "CUBE_RS Root CA",
            "ca_validity_days": 3650,  # 10 лет
            "client_cert_validity_days": 365,  # 1 год
            "key_size": 2048,
            "ca_cert_path": "/etc/cube_gateway/certs/ca.crt",
            "ca_key_path": "/etc/cube_gateway/certs/ca.key",
            "client_certs_dir": "/etc/cube_gateway/certs/clients/",
            "auto_generate_ca": True,
        }

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, encoding="utf-8") as f:
                    file_config = json.load(f)
                    default_config.update(file_config)
            else:
                # Создаем конфигурационный файл
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                logger.info(f"Создан конфиг CA: {self.config_path}")

        except Exception as e:
            logger.warning(f"Ошибка загрузки конфига CA: {e}")

        return default_config

    def load_or_create_ca(self):
        """Загрузка существующего CA или создание нового"""
        ca_cert_path = self.config["ca_cert_path"]
        ca_key_path = self.config["ca_key_path"]

        # Проверяем существование файлов CA
        if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
            try:
                self.load_existing_ca(ca_cert_path, ca_key_path)
                logger.info("Загружен существующий CA")
                return
            except Exception as e:
                logger.warning(f"Не удалось загрузить существующий CA: {e}")

        # Создаем новый CA если автогенерация включена
        if self.config.get("auto_generate_ca", True):
            self.create_new_ca()
            logger.info("Создан новый CA")
        else:
            logger.error("CA не найден и автогенерация отключена")
            raise ValueError("CA не настроен")

    def load_existing_ca(self, cert_path: str, key_path: str):
        """Загрузка существующего CA"""
        # Загружаем сертификат CA
        with open(cert_path, "rb") as f:
            self.ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        # Загружаем приватный ключ CA
        with open(key_path, "rb") as f:
            self.ca_private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )

        # Проверяем срок действия
        if datetime.now() > self.ca_cert.not_valid_after:
            logger.error("CA сертификат истек!")
            raise ValueError("CA certificate expired")

        if (self.ca_cert.not_valid_after - datetime.now()).days < 30:
            logger.warning("CA сертификат истекает через менее чем 30 дней!")

    def create_new_ca(self):
        """Создание нового CA"""
        # Генерируем приватный ключ
        self.ca_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.config["key_size"],
            backend=default_backend(),
        )

        # Создаем сертификат CA
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, self.config["ca_country"]),
                x509.NameAttribute(
                    NameOID.STATE_OR_PROVINCE_NAME, self.config["ca_state"]
                ),
                x509.NameAttribute(NameOID.LOCALITY_NAME, self.config["ca_locality"]),
                x509.NameAttribute(
                    NameOID.ORGANIZATION_NAME, self.config["ca_organization"]
                ),
                x509.NameAttribute(
                    NameOID.ORGANIZATIONAL_UNIT_NAME,
                    self.config["ca_organizational_unit"],
                ),
                x509.NameAttribute(NameOID.COMMON_NAME, self.config["ca_common_name"]),
            ]
        )

        self.ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.ca_private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now())
            .not_valid_after(
                datetime.now() + timedelta(days=self.config["ca_validity_days"])
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(
                    self.ca_private_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self.ca_private_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=False,
                    key_encipherment=False,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(self.ca_private_key, hashes.SHA256(), default_backend())
        )

        # Сохраняем CA файлы
        self.save_ca_files()

    def save_ca_files(self):
        """Сохранение файлов CA"""
        ca_cert_path = self.config["ca_cert_path"]
        ca_key_path = self.config["ca_key_path"]

        # Создаем директорию
        os.makedirs(os.path.dirname(ca_cert_path), exist_ok=True)

        # Сохраняем сертификат CA
        with open(ca_cert_path, "wb") as f:
            f.write(self.ca_cert.public_bytes(serialization.Encoding.PEM))

        # Сохраняем приватный ключ CA (без пароля для простоты в dev)
        with open(ca_key_path, "wb") as f:
            f.write(
                self.ca_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Устанавливаем права доступа
        os.chmod(ca_key_path, 0o600)  # Только владелец может читать
        os.chmod(ca_cert_path, 0o644)

        logger.info(f"CA сертификат сохранен: {ca_cert_path}")
        logger.info(f"CA ключ сохранен: {ca_key_path}")

    def create_client_certificate(
        self,
        device_id: str,
        common_name: str = None,
        ip_addresses: list = None,
        dns_names: list = None,
        validity_days: int = None,
    ) -> tuple[bytes, bytes]:
        """Создание клиентского сертификата для устройства"""

        if not self.ca_cert or not self.ca_private_key:
            raise ValueError("CA не инициализирован")

        validity_days = validity_days or self.config["client_cert_validity_days"]
        common_name = common_name or f"device-{device_id}"
        ip_addresses = ip_addresses or []
        dns_names = dns_names or []

        # Генерируем приватный ключ для клиента
        client_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.config["key_size"],
            backend=default_backend(),
        )

        # Создаем subject для клиентского сертификата
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, self.config["ca_country"]),
                x509.NameAttribute(
                    NameOID.ORGANIZATION_NAME, self.config["ca_organization"]
                ),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Devices"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )

        # Создаем альтернативные имена
        san_list = []
        for dns_name in dns_names:
            san_list.append(x509.DNSName(dns_name))
        for ip_addr in ip_addresses:
            try:
                san_list.append(x509.IPAddress(ipaddress.ip_address(ip_addr)))
            except ValueError:
                logger.warning(f"Некорректный IP адрес: {ip_addr}")

        # Строим сертификат
        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(client_private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now())
            .not_valid_after(datetime.now() + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(
                    client_private_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self.ca_private_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=False,
                    crl_sign=False,
                    digital_signature=True,
                    key_encipherment=True,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtensionOID.CLIENT_AUTH]),
                critical=True,
            )
        )

        # Добавляем Subject Alternative Name если есть
        if san_list:
            cert_builder = cert_builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )

        # Подписываем сертификат CA
        client_cert = cert_builder.sign(
            self.ca_private_key, hashes.SHA256(), default_backend()
        )

        # Возвращаем сертификат и ключ в PEM формате
        cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)
        key_pem = client_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return cert_pem, key_pem

    def save_client_certificate(self, device_id: str, cert_pem: bytes, key_pem: bytes):
        """Сохранение клиентского сертификата в файл"""
        clients_dir = self.config["client_certs_dir"]
        os.makedirs(clients_dir, exist_ok=True)

        cert_path = os.path.join(clients_dir, f"{device_id}.crt")
        key_path = os.path.join(clients_dir, f"{device_id}.key")

        with open(cert_path, "wb") as f:
            f.write(cert_pem)

        with open(key_path, "wb") as f:
            f.write(key_pem)

        # Устанавливаем права доступа
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)

        logger.info(f"Клиентский сертификат сохранен: {cert_path}")
        logger.info(f"Клиентский ключ сохранен: {key_path}")

        return cert_path, key_path


class MutualTLSClient:
    """HTTP клиент с поддержкой взаимной TLS аутентификации"""

    def __init__(
        self, client_cert_path: str, client_key_path: str, ca_cert_path: str = None
    ):
        self.client_cert_path = client_cert_path
        self.client_key_path = client_key_path
        self.ca_cert_path = ca_cert_path
        self.session = self.create_mtls_session()

    def create_mtls_session(self) -> requests.Session:
        """Создание сессии с mTLS"""
        session = requests.Session()

        # Настраиваем адаптер с mTLS
        adapter = MTLSAdapter(
            cert_file=self.client_cert_path,
            key_file=self.client_key_path,
            ca_file=self.ca_cert_path,
        )

        session.mount("https://", adapter)
        return session

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Выполнение mTLS запроса"""
        try:
            return self.session.request(method, url, **kwargs)
        except requests.exceptions.SSLError as e:
            if "certificate verify failed" in str(e).lower():
                logger.error(
                    "mTLS аутентификация не удалась - проверьте клиентский сертификат"
                )
            raise


class MTLSAdapter(HTTPAdapter):
    """HTTP адаптер с поддержкой взаимной TLS аутентификации"""

    def __init__(
        self, cert_file: str, key_file: str, ca_file: str = None, *args, **kwargs
    ):
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        """Инициализация pool manager с mTLS контекстом"""
        context = create_urllib3_context()

        # Настройка клиентского сертификата
        context.load_cert_chain(self.cert_file, self.key_file)

        # Настройка проверки сервера
        if self.ca_file:
            context.load_verify_locations(self.ca_file)
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


class MTLSServer:
    """Простой HTTPS сервер с поддержкой взаимной TLS аутентификации"""

    def __init__(
        self,
        server_cert_path: str,
        server_key_path: str,
        ca_cert_path: str,
        host: str = "localhost",
        port: int = 8443,
    ):
        self.server_cert_path = server_cert_path
        self.server_key_path = server_key_path
        self.ca_cert_path = ca_cert_path
        self.host = host
        self.port = port

    def create_ssl_context(self) -> ssl.SSLContext:
        """Создание SSL контекста для mTLS сервера"""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # Загружаем серверный сертификат
        context.load_cert_chain(self.server_cert_path, self.server_key_path)

        # Требуем клиентский сертификат
        context.verify_mode = ssl.CERT_REQUIRED

        # Загружаем CA для проверки клиентских сертификатов
        context.load_verify_locations(self.ca_cert_path)

        return context

    def handle_client(self, conn: ssl.SSLSocket, addr: tuple):
        """Обработка клиентского подключения"""
        try:
            # Получаем информацию о клиентском сертификате
            client_cert = conn.getpeercert()
            if client_cert:
                client_cn = dict(x[0] for x in client_cert["subject"])["commonName"]
                logger.info(f"Подключение от клиента: {client_cn} ({addr[0]})")

            # Простой HTTP ответ
            response = (
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nMutual TLS OK!\r\n"
            )
            conn.send(response)

        except Exception as e:
            logger.error(f"Ошибка обработки клиента {addr}: {e}")
        finally:
            conn.close()

    def start_server(self):
        """Запуск mTLS сервера"""
        context = self.create_ssl_context()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)

            logger.info(f"mTLS сервер запущен на {self.host}:{self.port}")

            with context.wrap_socket(sock, server_side=True) as ssock:
                while True:
                    try:
                        conn, addr = ssock.accept()
                        logger.info(f"Новое подключение от {addr}")
                        self.handle_client(conn, addr)
                    except ssl.SSLError as e:
                        logger.warning(f"SSL ошибка: {e}")
                    except KeyboardInterrupt:
                        logger.info("Остановка сервера")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка сервера: {e}")


def setup_device_mtls(
    device_id: str, server_host: str = "localhost"
) -> tuple[str, str]:
    """Настройка mTLS для устройства"""
    try:
        # Создаем CA
        ca = CertificateAuthority()

        # Создаем клиентский сертификат для устройства
        cert_pem, key_pem = ca.create_client_certificate(
            device_id=device_id,
            common_name=f"cube-gateway-{device_id}",
            dns_names=[server_host, "localhost"],
            ip_addresses=["127.0.0.1"],
        )

        # Сохраняем сертификат
        cert_path, key_path = ca.save_client_certificate(device_id, cert_pem, key_pem)

        logger.info(f"mTLS настроен для устройства {device_id}")
        return cert_path, key_path

    except Exception as e:
        logger.error(f"Ошибка настройки mTLS для {device_id}: {e}")
        raise


def main():
    """Демонстрация взаимной TLS аутентификации"""
    logging.basicConfig(level=logging.INFO)

    print("🔐 Mutual TLS Demo")

    # Настраиваем mTLS для тестового устройства
    device_id = "test-device-001"
    cert_path, key_path = setup_device_mtls(device_id)

    print(f"✅ Клиентский сертификат создан: {cert_path}")
    print(f"✅ Клиентский ключ создан: {key_path}")

    # Создаем mTLS клиент
    ca_cert_path = "/etc/cube_gateway/certs/ca.crt"
    client = MutualTLSClient(cert_path, key_path, ca_cert_path)

    print("🔒 mTLS клиент готов к использованию")


if __name__ == "__main__":
    main()
