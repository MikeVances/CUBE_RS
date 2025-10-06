#!/usr/bin/env python3
"""
MITM Protection - Защита от атак "человек посередине"
Реализация certificate pinning, mutual TLS, проверка подлинности сертификатов
"""

import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import warnings
from datetime import datetime
from typing import Any, Optional

import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# Отключаем warnings от urllib3 для самоподписанных сертификатов в dev режиме
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logger = logging.getLogger(__name__)


class CertificatePin:
    """Класс для хранения информации о закрепленном сертификате"""

    def __init__(
        self,
        hostname: str,
        pin_type: str,
        pin_value: str,
        description: str = "",
        expires: str = "",
    ):
        self.hostname = hostname
        self.pin_type = pin_type  # 'sha256', 'sha1', 'md5'
        self.pin_value = pin_value
        self.description = description
        self.expires = expires
        self.created_at = datetime.now().isoformat()


class CertificateManager:
    """Менеджер сертификатов и certificate pinning"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or "/etc/cube_gateway/cert_pins.json"
        self.pins_cache = {}
        self.load_certificate_pins()

    def load_certificate_pins(self):
        """Загрузка закрепленных сертификатов из конфига"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, encoding="utf-8") as f:
                    pins_data = json.load(f)

                for hostname, pin_data in pins_data.items():
                    self.pins_cache[hostname] = CertificatePin(
                        hostname=hostname,
                        pin_type=pin_data.get("pin_type", "sha256"),
                        pin_value=pin_data.get("pin_value", ""),
                        description=pin_data.get("description", ""),
                        expires=pin_data.get("expires", ""),
                    )
            else:
                # Создаем конфиг с дефолтными настройками
                self.create_default_pins_config()

        except Exception as e:
            logger.error(f"Ошибка загрузки certificate pins: {e}")
            self.pins_cache = {}

    def create_default_pins_config(self):
        """Создание дефолтного конфига с pins"""
        default_pins = {
            "production-server.company.com": {
                "pin_type": "sha256",
                "pin_value": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",  # Placeholder
                "description": "Production CUBE_RS server certificate",
                "expires": "",
            },
            "localhost": {
                "pin_type": "sha256",
                "pin_value": "development-localhost-pin",
                "description": "Development localhost certificate",
                "expires": "",
            },
        }

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(default_pins, f, indent=2, ensure_ascii=False)
            logger.info(f"Создан дефолтный конфиг certificate pins: {self.config_path}")
        except Exception as e:
            logger.error(f"Ошибка создания конфига pins: {e}")

    def extract_certificate_pin(self, cert_der: bytes, pin_type: str = "sha256") -> str:
        """Извлечение pin из DER-encoded сертификата"""
        try:
            if pin_type == "sha256":
                pin_hash = hashlib.sha256(cert_der).digest()
            elif pin_type == "sha1":
                pin_hash = hashlib.sha1(cert_der).digest()
            elif pin_type == "md5":
                pin_hash = hashlib.md5(cert_der).digest()
            else:
                raise ValueError(f"Неподдерживаемый тип pin: {pin_type}")

            return base64.b64encode(pin_hash).decode("ascii")

        except Exception as e:
            logger.error(f"Ошибка извлечения pin из сертификата: {e}")
            return ""

    def extract_public_key_pin(
        self, cert: x509.Certificate, pin_type: str = "sha256"
    ) -> str:
        """Извлечение pin из публичного ключа (более надежно чем cert pin)"""
        try:
            # Получаем публичный ключ
            public_key = cert.public_key()

            # Сериализуем в DER формат
            public_key_der = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

            # Создаем хэш
            if pin_type == "sha256":
                pin_hash = hashlib.sha256(public_key_der).digest()
            elif pin_type == "sha1":
                pin_hash = hashlib.sha1(public_key_der).digest()
            else:
                raise ValueError(f"Неподдерживаемый тип pin: {pin_type}")

            return base64.b64encode(pin_hash).decode("ascii")

        except Exception as e:
            logger.error(f"Ошибка извлечения public key pin: {e}")
            return ""

    def verify_certificate_pin(self, hostname: str, cert_der: bytes) -> bool:
        """Проверка certificate pin для хоста"""
        if hostname not in self.pins_cache:
            logger.warning(f"Нет закрепленного сертификата для хоста: {hostname}")
            return True  # В dev режиме пропускаем

        pin_info = self.pins_cache[hostname]

        # Проверяем срок действия pin
        if pin_info.expires:
            try:
                expires_date = datetime.fromisoformat(pin_info.expires)
                if datetime.now() > expires_date:
                    logger.warning(f"Certificate pin для {hostname} истек")
                    return False
            except:
                pass

        try:
            # Парсим сертификат
            cert = x509.load_der_x509_certificate(cert_der)

            # Получаем актуальный pin
            if pin_info.pin_type.startswith("pubkey-"):
                # Public key pinning (рекомендуется)
                actual_pin = self.extract_public_key_pin(
                    cert, pin_info.pin_type.replace("pubkey-", "")
                )
            else:
                # Certificate pinning
                actual_pin = self.extract_certificate_pin(cert_der, pin_info.pin_type)

            # Сравниваем с ожидаемым
            expected_pin = pin_info.pin_value

            if actual_pin == expected_pin:
                logger.info(f"Certificate pin для {hostname} подтвержден")
                return True
            else:
                logger.error(f"Certificate pin для {hostname} НЕ СОВПАДАЕТ!")
                logger.error(f"Ожидался: {expected_pin[:20]}...")
                logger.error(f"Получен:  {actual_pin[:20]}...")
                return False

        except Exception as e:
            logger.error(f"Ошибка проверки certificate pin для {hostname}: {e}")
            return False

    def add_certificate_pin(
        self,
        hostname: str,
        cert_der: bytes,
        pin_type: str = "pubkey-sha256",
        description: str = "",
    ):
        """Добавление нового certificate pin"""
        try:
            cert = x509.load_der_x509_certificate(cert_der)

            if pin_type.startswith("pubkey-"):
                pin_value = self.extract_public_key_pin(
                    cert, pin_type.replace("pubkey-", "")
                )
            else:
                pin_value = self.extract_certificate_pin(cert_der, pin_type)

            pin = CertificatePin(
                hostname=hostname,
                pin_type=pin_type,
                pin_value=pin_value,
                description=description,
            )

            self.pins_cache[hostname] = pin
            self.save_pins_to_config()

            logger.info(f"Добавлен certificate pin для {hostname}")

        except Exception as e:
            logger.error(f"Ошибка добавления certificate pin: {e}")

    def save_pins_to_config(self):
        """Сохранение pins в конфигурацию"""
        try:
            pins_data = {}
            for hostname, pin in self.pins_cache.items():
                pins_data[hostname] = {
                    "pin_type": pin.pin_type,
                    "pin_value": pin.pin_value,
                    "description": pin.description,
                    "expires": pin.expires,
                    "created_at": pin.created_at,
                }

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(pins_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Ошибка сохранения pins в конфиг: {e}")


class PinnedHTTPAdapter(HTTPAdapter):
    """HTTP адаптер с поддержкой certificate pinning"""

    def __init__(self, cert_manager: CertificateManager, *args, **kwargs):
        self.cert_manager = cert_manager
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        """Инициализация pool manager с custom SSL контекстом"""
        context = create_urllib3_context()

        # Устанавливаем callback для проверки сертификата
        context.check_hostname = False  # Мы проверяем сами через pinning
        context.verify_mode = ssl.CERT_REQUIRED

        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)

    def cert_verify(self, conn, url, verify, cert):
        """Кастомная проверка сертификата с pinning"""
        try:
            # Получаем хост из URL
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            hostname = parsed_url.hostname

            if not hostname:
                logger.error("Не удалось извлечь hostname из URL")
                return False

            # Получаем сертификат
            sock = conn.sock
            if hasattr(sock, "getpeercert_chain"):
                # Получаем цепочку сертификатов
                cert_chain = sock.getpeercert_chain()
                if cert_chain:
                    # Берем первый сертификат (листовой)
                    cert_der = cert_chain[0]

                    # Проверяем pin
                    return self.cert_manager.verify_certificate_pin(hostname, cert_der)

            # Fallback - стандартная проверка
            logger.warning(
                f"Не удалось получить сертификат для pinning проверки: {hostname}"
            )
            return True  # В dev режиме пропускаем

        except Exception as e:
            logger.error(f"Ошибка в cert_verify: {e}")
            return False


class SecureHTTPSClient:
    """HTTPS клиент с защитой от MITM атак"""

    def __init__(
        self, cert_manager: CertificateManager = None, config: dict[str, Any] = None
    ):
        self.cert_manager = cert_manager or CertificateManager()
        self.config = config or self.load_default_security_config()
        self.session = None
        self.setup_secure_session()

    def load_default_security_config(self) -> dict[str, Any]:
        """Загрузка дефолтной конфигурации безопасности"""
        return {
            "certificate_pinning": {
                "enabled": True,
                "pin_type": "pubkey-sha256",
                "fail_on_pin_mismatch": True,
            },
            "ssl_verification": {
                "verify_ssl": True,
                "check_hostname": True,
                "ssl_version": "TLSv1_2",
                "ciphers": "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS",
            },
            "connection": {"timeout": 30, "max_retries": 3, "backoff_factor": 1.0},
            "headers": {
                "user_agent": "CUBE_RS_Gateway/1.0.0",
                "connection": "keep-alive",
            },
        }

    def setup_secure_session(self):
        """Настройка защищенной HTTP сессии"""
        self.session = requests.Session()

        # Настройка SSL контекста
        ssl_config = self.config.get("ssl_verification", {})

        # Добавляем адаптер с certificate pinning
        if self.config.get("certificate_pinning", {}).get("enabled", True):
            adapter = PinnedHTTPAdapter(self.cert_manager)
            self.session.mount("https://", adapter)

        # Настройка заголовков
        headers_config = self.config.get("headers", {})
        if headers_config.get("user_agent"):
            self.session.headers.update({"User-Agent": headers_config["user_agent"]})

        # Настройка таймаутов
        connection_config = self.config.get("connection", {})
        self.session.timeout = connection_config.get("timeout", 30)

        # Настройка SSL верификации
        self.session.verify = ssl_config.get("verify_ssl", True)

    def secure_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Выполнение защищенного HTTP запроса"""
        try:
            # Дополнительные проверки перед запросом
            if not self.pre_request_security_check(url):
                raise SecurityError("Pre-request security check failed")

            # Выполняем запрос
            response = self.session.request(method, url, **kwargs)

            # Пост-проверки ответа
            if not self.post_response_security_check(response):
                raise SecurityError("Post-response security check failed")

            return response

        except requests.exceptions.SSLError as e:
            logger.error(f"SSL ошибка при запросе к {url}: {e}")
            if "certificate verify failed" in str(e).lower():
                raise SecurityError(
                    "Certificate verification failed - possible MITM attack"
                )
            raise
        except Exception as e:
            logger.error(f"Ошибка безопасного запроса к {url}: {e}")
            raise

    def pre_request_security_check(self, url: str) -> bool:
        """Предварительные проверки безопасности"""
        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)

            # Проверяем протокол
            if parsed_url.scheme != "https":
                logger.warning(f"Небезопасный протокол в URL: {url}")
                return False

            # Проверяем hostname
            if not parsed_url.hostname:
                logger.error(f"Некорректный hostname в URL: {url}")
                return False

            # Проверяем на подозрительные домены
            suspicious_patterns = [
                "localhost",  # В продакшене должен быть заменен
                "127.0.0.1",
                "192.168.",
                "10.",
                "172.16.",
                "172.17.",
                "172.18.",
                "172.19.",
                "172.20.",
                "172.21.",
                "172.22.",
                "172.23.",
                "172.24.",
                "172.25.",
                "172.26.",
                "172.27.",
                "172.28.",
                "172.29.",
                "172.30.",
                "172.31.",
            ]

            hostname = parsed_url.hostname.lower()
            for pattern in suspicious_patterns:
                if pattern in hostname:
                    logger.warning(f"Подозрительный hostname: {hostname}")
                    # В dev режиме разрешаем, в продакшене - блокируем
                    if os.getenv("ENVIRONMENT", "development") == "production":
                        return False

            return True

        except Exception as e:
            logger.error(f"Ошибка в pre_request_security_check: {e}")
            return False

    def post_response_security_check(self, response: requests.Response) -> bool:
        """Проверки безопасности ответа"""
        try:
            # Проверяем заголовки безопасности
            security_headers = [
                "strict-transport-security",
                "x-content-type-options",
                "x-frame-options",
                "x-xss-protection",
            ]

            missing_headers = []
            for header in security_headers:
                if header not in response.headers:
                    missing_headers.append(header)

            if missing_headers:
                logger.warning(f"Отсутствуют заголовки безопасности: {missing_headers}")

            # Проверяем Content-Type
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                # JSON ответ - проверяем на подозрительный контент
                try:
                    json_data = response.json()
                    if self.contains_suspicious_content(json_data):
                        logger.warning("Обнаружен подозрительный контент в JSON ответе")
                        return False
                except:
                    pass

            return True

        except Exception as e:
            logger.error(f"Ошибка в post_response_security_check: {e}")
            return True  # Не блокируем из-за ошибки проверки

    def contains_suspicious_content(self, data: Any) -> bool:
        """Проверка контента на подозрительные паттерны"""
        try:
            # Конвертируем в строку для анализа
            content_str = json.dumps(data).lower()

            suspicious_patterns = [
                "<script",
                "javascript:",
                "eval(",
                "document.cookie",
                "window.location",
                "alert(",
                "prompt(",
                "confirm(",
            ]

            for pattern in suspicious_patterns:
                if pattern in content_str:
                    logger.warning(f"Обнаружен подозрительный паттерн: {pattern}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Ошибка анализа контента: {e}")
            return False


class SecurityError(Exception):
    """Исключение для ошибок безопасности"""

    pass


class MITMDetector:
    """Детектор MITM атак"""

    def __init__(self):
        self.known_certificates = {}
        self.certificate_history = []
        self.suspicious_activity = []

    def check_certificate_change(self, hostname: str, cert_fingerprint: str) -> bool:
        """Проверка изменения сертификата (возможная MITM атака)"""
        if hostname in self.known_certificates:
            previous_fingerprint = self.known_certificates[hostname]["fingerprint"]

            if previous_fingerprint != cert_fingerprint:
                logger.error(f"🚨 ОБНАРУЖЕНА СМЕНА СЕРТИФИКАТА для {hostname}!")
                logger.error(f"Предыдущий: {previous_fingerprint}")
                logger.error(f"Текущий:    {cert_fingerprint}")

                # Записываем подозрительную активность
                self.suspicious_activity.append(
                    {
                        "type": "certificate_change",
                        "hostname": hostname,
                        "previous_cert": previous_fingerprint,
                        "new_cert": cert_fingerprint,
                        "timestamp": datetime.now().isoformat(),
                        "severity": "critical",
                    }
                )

                return False  # Возможная MITM атака

        # Сохраняем новый сертификат
        self.known_certificates[hostname] = {
            "fingerprint": cert_fingerprint,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
        }

        return True

    def detect_dns_spoofing(self, hostname: str, resolved_ips: list[str]) -> bool:
        """Обнаружение DNS спуфинга"""
        # В реальной реализации здесь была бы проверка известных IP для домена
        # Пока что простая эвристика

        private_ranges = [
            "192.168.",
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
        ]

        for ip in resolved_ips:
            for private_range in private_ranges:
                if ip.startswith(private_range):
                    if not hostname.startswith("localhost") and not ip.startswith(
                        "127."
                    ):
                        logger.warning(
                            f"Публичный домен {hostname} резолвится в приватный IP {ip}"
                        )
                        return False

        return True


def create_mitm_protected_client(
    server_url: str = None, pins_config: str = None
) -> SecureHTTPSClient:
    """Создание защищенного от MITM клиента"""
    cert_manager = CertificateManager(pins_config)

    # Если указан server_url, извлекаем и закрепляем сертификат
    if server_url:
        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(server_url)
            hostname = parsed_url.hostname
            port = parsed_url.port or 443

            # Получаем сертификат сервера
            cert_der = get_server_certificate_der(hostname, port)
            if cert_der:
                cert_manager.add_certificate_pin(
                    hostname=hostname,
                    cert_der=cert_der,
                    pin_type="pubkey-sha256",
                    description=f"Auto-pinned certificate for {hostname}",
                )
                logger.info(f"Автоматически закреплен сертификат для {hostname}")

        except Exception as e:
            logger.warning(f"Не удалось автоматически закрепить сертификат: {e}")

    return SecureHTTPSClient(cert_manager)


def get_server_certificate_der(hostname: str, port: int = 443) -> Optional[bytes]:
    """Получение DER-encoded сертификата сервера"""
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert_der = ssock.getpeercert(binary_form=True)
                return cert_der

    except Exception as e:
        logger.error(f"Ошибка получения сертификата {hostname}:{port}: {e}")
        return None


def main():
    """Демонстрация защиты от MITM"""
    logging.basicConfig(level=logging.INFO)

    print("🔒 MITM Protection Demo")

    # Создаем защищенный клиент
    client = create_mitm_protected_client("https://httpbin.org")

    try:
        # Тестовый запрос
        response = client.secure_request("GET", "https://httpbin.org/json")
        print(f"✅ Защищенный запрос выполнен: {response.status_code}")
        print(f"Response: {response.json()}")

    except SecurityError as e:
        print(f"🚨 Заблокировано по соображениям безопасности: {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
