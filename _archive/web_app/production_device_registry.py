#!/usr/bin/env python3
"""
Production Device Registry - расширение DeviceRegistry для продакшена
Поддержка массовой подготовки устройств и активации в поле
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .device_registry import (
    DeviceRegistrationRequest,
    DeviceRegistry,
)

logger = logging.getLogger(__name__)


@dataclass
class ProductionBatch:
    """Производственная партия устройств"""

    batch_id: str
    batch_name: str
    created_time: str
    created_by: str
    device_count: int
    device_type: str
    tags: list[str]
    target_deployment: str  # production, testing, staging
    hardware_specs: dict[str, Any]
    notes: str = ""
    status: str = "created"  # created, prepared, deployed, completed


@dataclass
class PreSharedDevice:
    """Предподготовленное устройство с предустановленным ключом"""

    device_serial: str
    batch_id: str
    auth_key_hash: str
    device_type: str
    hardware_id: str  # MAC, Serial, или другой уникальный ID
    activation_token: str  # Токен для активации в поле
    created_time: str
    activated_time: str = ""
    status: str = "prepared"  # prepared, activated, registered, deployed


@dataclass
class HardwareBinding:
    """Привязка устройства к железу для безопасности"""

    device_id: str
    hardware_signature: str  # Хэш характеристик железа
    mac_addresses: list[str]
    cpu_serial: str = ""
    disk_serial: str = ""
    board_serial: str = ""
    binding_time: str = ""
    is_verified: bool = False


class ProductionDeviceRegistry(DeviceRegistry):
    """Расширенный реестр для продакшен развертывания"""

    def __init__(self, db_path: str = "production_device_registry.db"):
        super().__init__(db_path)
        self.init_production_tables()

    def init_production_tables(self):
        """Инициализация дополнительных таблиц для продакшена"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Таблица производственных партий
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS production_batches (
                        batch_id TEXT PRIMARY KEY,
                        batch_name TEXT NOT NULL,
                        created_time TEXT NOT NULL,
                        created_by TEXT NOT NULL,
                        device_count INTEGER NOT NULL,
                        device_type TEXT NOT NULL,
                        tags TEXT DEFAULT '[]',
                        target_deployment TEXT DEFAULT 'production',
                        hardware_specs TEXT DEFAULT '{}',
                        notes TEXT DEFAULT '',
                        status TEXT DEFAULT 'created',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Таблица предподготовленных устройств
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pre_shared_devices (
                        device_serial TEXT PRIMARY KEY,
                        batch_id TEXT NOT NULL,
                        auth_key_hash TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        hardware_id TEXT NOT NULL UNIQUE,
                        activation_token TEXT NOT NULL UNIQUE,
                        created_time TEXT NOT NULL,
                        activated_time TEXT DEFAULT '',
                        status TEXT DEFAULT 'prepared',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (batch_id) REFERENCES production_batches (batch_id),
                        FOREIGN KEY (auth_key_hash) REFERENCES auth_keys (key_hash)
                    )
                """
                )

                # Таблица привязки к железу
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hardware_bindings (
                        device_id TEXT PRIMARY KEY,
                        hardware_signature TEXT NOT NULL,
                        mac_addresses TEXT NOT NULL,
                        cpu_serial TEXT DEFAULT '',
                        disk_serial TEXT DEFAULT '',
                        board_serial TEXT DEFAULT '',
                        binding_time TEXT DEFAULT '',
                        is_verified BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (device_id) REFERENCES registered_devices (device_id)
                    )
                """
                )

                # Индексы для производительности
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_batches_status ON production_batches(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_batches_type ON production_batches(device_type)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pre_devices_status ON pre_shared_devices(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pre_devices_batch ON pre_shared_devices(batch_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_hardware_verified ON hardware_bindings(is_verified)"
                )

                conn.commit()
                logger.info("Таблицы продакшен реестра инициализированы")

        except Exception as e:
            logger.error(f"Ошибка инициализации продакшен таблиц: {e}")
            raise

    def create_production_batch(
        self,
        batch_name: str,
        device_count: int,
        device_type: str = "gateway",
        tags: list[str] = None,
        target_deployment: str = "production",
        hardware_specs: dict[str, Any] = None,
        created_by: str = "system",
        notes: str = "",
    ) -> str:
        """Создание производственной партии"""
        if tags is None:
            tags = ["production", "batch"]
        if hardware_specs is None:
            hardware_specs = {}

        batch_id = f"batch_{secrets.token_urlsafe(12)}"

        batch = ProductionBatch(
            batch_id=batch_id,
            batch_name=batch_name,
            created_time=datetime.now().isoformat(),
            created_by=created_by,
            device_count=device_count,
            device_type=device_type,
            tags=tags,
            target_deployment=target_deployment,
            hardware_specs=hardware_specs,
            notes=notes,
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO production_batches
                    (batch_id, batch_name, created_time, created_by, device_count, device_type,
                     tags, target_deployment, hardware_specs, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        batch.batch_id,
                        batch.batch_name,
                        batch.created_time,
                        batch.created_by,
                        batch.device_count,
                        batch.device_type,
                        json.dumps(batch.tags),
                        batch.target_deployment,
                        json.dumps(batch.hardware_specs),
                        batch.notes,
                        batch.status,
                    ),
                )
                conn.commit()

                logger.info(
                    f"Создана производственная партия {batch_id}: {device_count} устройств"
                )
                return batch_id

        except Exception as e:
            logger.error(f"Ошибка создания производственной партии: {e}")
            raise

    def prepare_batch_devices(self, batch_id: str) -> list[dict[str, str]]:
        """Подготовка устройств в партии - создание ключей и токенов активации"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Получаем информацию о партии
                cursor = conn.execute(
                    "SELECT * FROM production_batches WHERE batch_id = ?", (batch_id,)
                )
                batch_row = cursor.fetchone()

                if not batch_row:
                    raise ValueError(f"Партия {batch_id} не найдена")

                batch_data = ProductionBatch(
                    batch_id=batch_row[0],
                    batch_name=batch_row[1],
                    created_time=batch_row[2],
                    created_by=batch_row[3],
                    device_count=batch_row[4],
                    device_type=batch_row[5],
                    tags=json.loads(batch_row[6]),
                    target_deployment=batch_row[7],
                    hardware_specs=json.loads(batch_row[8]),
                    notes=batch_row[9] or "",
                    status=batch_row[10],
                )

                if batch_data.status != "created":
                    raise ValueError(
                        f"Партия {batch_id} уже подготовлена или обработана"
                    )

                # Создаем устройства
                prepared_devices = []

                for i in range(batch_data.device_count):
                    # Генерируем auth key для каждого устройства
                    auth_key = self.generate_auth_key(
                        expires_hours=0,  # Бессрочный ключ
                        max_usage=1,  # Однократное использование
                        is_reusable=False,
                        is_ephemeral=False,
                        tags=batch_data.tags,
                        created_by=batch_data.created_by,
                    )

                    # Создаем запись предподготовленного устройства
                    device_serial = f"{batch_data.batch_name}-{i+1:04d}"
                    hardware_id = f"HW_{secrets.token_urlsafe(16)}"
                    activation_token = secrets.token_urlsafe(24)
                    key_hash = hashlib.sha256(auth_key.encode()).hexdigest()

                    pre_device = PreSharedDevice(
                        device_serial=device_serial,
                        batch_id=batch_id,
                        auth_key_hash=key_hash,
                        device_type=batch_data.device_type,
                        hardware_id=hardware_id,
                        activation_token=activation_token,
                        created_time=datetime.now().isoformat(),
                    )

                    conn.execute(
                        """
                        INSERT INTO pre_shared_devices
                        (device_serial, batch_id, auth_key_hash, device_type, hardware_id,
                         activation_token, created_time, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            pre_device.device_serial,
                            pre_device.batch_id,
                            pre_device.auth_key_hash,
                            pre_device.device_type,
                            pre_device.hardware_id,
                            pre_device.activation_token,
                            pre_device.created_time,
                            pre_device.status,
                        ),
                    )

                    prepared_devices.append(
                        {
                            "device_serial": device_serial,
                            "auth_key": auth_key,
                            "activation_token": activation_token,
                            "hardware_id": hardware_id,
                        }
                    )

                # Обновляем статус партии
                conn.execute(
                    """
                    UPDATE production_batches
                    SET status = 'prepared', updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = ?
                """,
                    (batch_id,),
                )

                conn.commit()

                logger.info(
                    f"Подготовлена партия {batch_id}: {len(prepared_devices)} устройств"
                )
                return prepared_devices

        except Exception as e:
            logger.error(f"Ошибка подготовки партии {batch_id}: {e}")
            raise

    def activate_device_in_field(
        self,
        activation_token: str,
        hardware_signature: dict[str, str],
        installer_id: str = "field-installer",
    ) -> dict[str, Any]:
        """Активация устройства в поле по токену активации"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Ищем устройство по токену активации
                cursor = conn.execute(
                    """
                    SELECT * FROM pre_shared_devices WHERE activation_token = ? AND status = 'prepared'
                """,
                    (activation_token,),
                )

                device_row = cursor.fetchone()
                if not device_row:
                    raise ValueError(
                        "Недействительный токен активации или устройство уже активировано"
                    )

                # Парсим данные устройства
                pre_device = PreSharedDevice(
                    device_serial=device_row[0],
                    batch_id=device_row[1],
                    auth_key_hash=device_row[2],
                    device_type=device_row[3],
                    hardware_id=device_row[4],
                    activation_token=device_row[5],
                    created_time=device_row[6],
                    activated_time=device_row[7],
                    status=device_row[8],
                )

                # Создаем подпись железа
                hw_signature_str = json.dumps(hardware_signature, sort_keys=True)
                hw_hash = hashlib.sha256(hw_signature_str.encode()).hexdigest()

                # Обновляем статус предподготовленного устройства
                now = datetime.now().isoformat()
                conn.execute(
                    """
                    UPDATE pre_shared_devices
                    SET status = 'activated', activated_time = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE activation_token = ?
                """,
                    (now, activation_token),
                )

                # Создаем запрос на регистрацию от имени активированного устройства
                # Получаем auth key по хэшу
                cursor = conn.execute(
                    "SELECT * FROM auth_keys WHERE key_hash = ?",
                    (pre_device.auth_key_hash,),
                )
                key_row = cursor.fetchone()
                if not key_row:
                    raise ValueError("Auth key не найден в системе")

                # Создаем запрос на регистрацию
                registration_request = DeviceRegistrationRequest(
                    request_id=secrets.token_urlsafe(16),
                    auth_key_hash=pre_device.auth_key_hash,
                    device_hostname=pre_device.device_serial,
                    device_type=pre_device.device_type,
                    device_info={
                        "hardware_signature": hardware_signature,
                        "hardware_id": pre_device.hardware_id,
                        "activation_token": activation_token,
                        "activated_by": installer_id,
                        "activation_method": "field_activation",
                    },
                    requested_time=now,
                    tailscale_ip="",  # Будет заполнено позже
                    status="pending",
                )

                conn.execute(
                    """
                    INSERT INTO device_registration_requests
                    (request_id, auth_key_hash, device_hostname, device_type, device_info,
                     requested_time, tailscale_ip, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        registration_request.request_id,
                        registration_request.auth_key_hash,
                        registration_request.device_hostname,
                        registration_request.device_type,
                        json.dumps(registration_request.device_info),
                        registration_request.requested_time,
                        registration_request.tailscale_ip,
                        registration_request.status,
                    ),
                )

                # Обновляем счетчик использования auth key
                conn.execute(
                    """
                    UPDATE auth_keys
                    SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE key_hash = ?
                """,
                    (pre_device.auth_key_hash,),
                )

                conn.commit()

                logger.info(
                    f"Устройство {pre_device.device_serial} активировано в поле, создан запрос {registration_request.request_id}"
                )

                return {
                    "device_serial": pre_device.device_serial,
                    "registration_request_id": registration_request.request_id,
                    "status": "activated",
                    "next_step": "pending_approval",
                }

        except Exception as e:
            logger.error(f"Ошибка активации устройства: {e}")
            raise

    def approve_production_registration(
        self, request_id: str, approved_by: str = "system", tailscale_ip: str = ""
    ) -> bool:
        """Одобрение регистрации продакшен устройства с привязкой к железу"""
        try:
            # Используем базовый метод одобрения
            success = self.approve_registration_request(request_id, approved_by)
            if not success:
                return False

            with sqlite3.connect(self.db_path) as conn:
                # Получаем информацию о созданном устройстве
                cursor = conn.execute(
                    """
                    SELECT rd.device_id, rd.metadata, drr.device_info
                    FROM registered_devices rd
                    JOIN device_registration_requests drr ON rd.auth_key_hash = drr.auth_key_hash
                    WHERE drr.request_id = ? AND drr.status = 'approved'
                """,
                    (request_id,),
                )

                row = cursor.fetchone()
                if not row:
                    logger.error(
                        f"Не удалось найти одобренное устройство для запроса {request_id}"
                    )
                    return False

                device_id, metadata_json, device_info_json = row
                device_info = json.loads(device_info_json)

                # Создаем привязку к железу, если есть подпись железа
                if "hardware_signature" in device_info:
                    hw_signature = device_info["hardware_signature"]

                    # Извлекаем MAC адреса
                    mac_addresses = hw_signature.get("mac_addresses", [])

                    # Создаем подпись железа
                    hw_signature_str = json.dumps(hw_signature, sort_keys=True)
                    hw_hash = hashlib.sha256(hw_signature_str.encode()).hexdigest()

                    hardware_binding = HardwareBinding(
                        device_id=device_id,
                        hardware_signature=hw_hash,
                        mac_addresses=mac_addresses,
                        cpu_serial=hw_signature.get("cpu_serial", ""),
                        disk_serial=hw_signature.get("disk_serial", ""),
                        board_serial=hw_signature.get("board_serial", ""),
                        binding_time=datetime.now().isoformat(),
                        is_verified=True,
                    )

                    conn.execute(
                        """
                        INSERT INTO hardware_bindings
                        (device_id, hardware_signature, mac_addresses, cpu_serial, disk_serial,
                         board_serial, binding_time, is_verified)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            hardware_binding.device_id,
                            hardware_binding.hardware_signature,
                            json.dumps(hardware_binding.mac_addresses),
                            hardware_binding.cpu_serial,
                            hardware_binding.disk_serial,
                            hardware_binding.board_serial,
                            hardware_binding.binding_time,
                            hardware_binding.is_verified,
                        ),
                    )

                    # Обновляем статус предподготовленного устройства
                    if "activation_token" in device_info:
                        conn.execute(
                            """
                            UPDATE pre_shared_devices
                            SET status = 'registered', updated_at = CURRENT_TIMESTAMP
                            WHERE activation_token = ?
                        """,
                            (device_info["activation_token"],),
                        )

                    # Обновляем IP адрес если предоставлен
                    if tailscale_ip:
                        conn.execute(
                            """
                            UPDATE registered_devices
                            SET tailscale_ip = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE device_id = ?
                        """,
                            (tailscale_ip, device_id),
                        )

                conn.commit()

                logger.info(
                    f"Продакшен регистрация {request_id} одобрена с привязкой к железу"
                )
                return True

        except Exception as e:
            logger.error(f"Ошибка одобрения продакшен регистрации: {e}")
            return False

    def get_production_batches(self, status: str = None) -> list[ProductionBatch]:
        """Получение производственных партий"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = "SELECT * FROM production_batches"
                params = []

                if status:
                    query += " WHERE status = ?"
                    params.append(status)

                query += " ORDER BY created_at DESC"

                cursor = conn.execute(query, params)

                batches = []
                for row in cursor.fetchall():
                    batch = ProductionBatch(
                        batch_id=row[0],
                        batch_name=row[1],
                        created_time=row[2],
                        created_by=row[3],
                        device_count=row[4],
                        device_type=row[5],
                        tags=json.loads(row[6] or "[]"),
                        target_deployment=row[7],
                        hardware_specs=json.loads(row[8] or "{}"),
                        notes=row[9] or "",
                        status=row[10],
                    )
                    batches.append(batch)

                return batches

        except Exception as e:
            logger.error(f"Ошибка получения производственных партий: {e}")
            return []

    def get_batch_devices(self, batch_id: str) -> list[PreSharedDevice]:
        """Получение устройств в партии"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM pre_shared_devices WHERE batch_id = ?
                    ORDER BY device_serial
                """,
                    (batch_id,),
                )

                devices = []
                for row in cursor.fetchall():
                    device = PreSharedDevice(
                        device_serial=row[0],
                        batch_id=row[1],
                        auth_key_hash=row[2],
                        device_type=row[3],
                        hardware_id=row[4],
                        activation_token=row[5],
                        created_time=row[6],
                        activated_time=row[7] or "",
                        status=row[8],
                    )
                    devices.append(device)

                return devices

        except Exception as e:
            logger.error(f"Ошибка получения устройств партии {batch_id}: {e}")
            return []

    def verify_hardware_binding(
        self, device_id: str, current_hw_signature: dict[str, str]
    ) -> bool:
        """Проверка привязки устройства к железу"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT hardware_signature FROM hardware_bindings
                    WHERE device_id = ? AND is_verified = 1
                """,
                    (device_id,),
                )

                row = cursor.fetchone()
                if not row:
                    logger.warning(
                        f"Привязка к железу для устройства {device_id} не найдена"
                    )
                    return False

                # Создаем подпись текущего железа
                current_hw_str = json.dumps(current_hw_signature, sort_keys=True)
                current_hw_hash = hashlib.sha256(current_hw_str.encode()).hexdigest()

                stored_hw_hash = row[0]

                if current_hw_hash == stored_hw_hash:
                    logger.info(
                        f"Привязка к железу для устройства {device_id} подтверждена"
                    )
                    return True
                else:
                    logger.warning(
                        f"Привязка к железу для устройства {device_id} не совпадает!"
                    )
                    return False

        except Exception as e:
            logger.error(f"Ошибка проверки привязки к железу: {e}")
            return False

    def get_production_stats(self) -> dict[str, Any]:
        """Получение статистики продакшен развертывания"""
        try:
            # Получаем базовую статистику
            base_stats = self.get_device_stats()

            with sqlite3.connect(self.db_path) as conn:
                # Статистика партий
                cursor = conn.execute("SELECT COUNT(*) FROM production_batches")
                total_batches = cursor.fetchone()[0]

                cursor = conn.execute(
                    "SELECT status, COUNT(*) FROM production_batches GROUP BY status"
                )
                batches_by_status = dict(cursor.fetchall())

                # Статистика предподготовленных устройств
                cursor = conn.execute("SELECT COUNT(*) FROM pre_shared_devices")
                total_pre_devices = cursor.fetchone()[0]

                cursor = conn.execute(
                    "SELECT status, COUNT(*) FROM pre_shared_devices GROUP BY status"
                )
                pre_devices_by_status = dict(cursor.fetchall())

                # Статистика привязки к железу
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM hardware_bindings WHERE is_verified = 1"
                )
                verified_bindings = cursor.fetchone()[0]

                production_stats = {
                    "total_production_batches": total_batches,
                    "batches_by_status": batches_by_status,
                    "total_pre_shared_devices": total_pre_devices,
                    "pre_devices_by_status": pre_devices_by_status,
                    "verified_hardware_bindings": verified_bindings,
                    "production_timestamp": datetime.now().isoformat(),
                }

                # Объединяем с базовой статистикой
                base_stats.update(production_stats)
                return base_stats

        except Exception as e:
            logger.error(f"Ошибка получения продакшен статистики: {e}")
            return {}


# Глобальный экземпляр продакшен реестра
_production_registry: Optional[ProductionDeviceRegistry] = None


def get_production_registry() -> ProductionDeviceRegistry:
    """Получение глобального экземпляра продакшен реестра"""
    global _production_registry
    if not _production_registry:
        db_path = os.path.join(
            os.path.dirname(__file__), "production_device_registry.db"
        )
        _production_registry = ProductionDeviceRegistry(db_path)
    return _production_registry


# Пример использования
if __name__ == "__main__":
    registry = ProductionDeviceRegistry("test_production_registry.db")

    print("=== Тест продакшен системы регистрации устройств ===")

    # Создание производственной партии
    print("1. Создание производственной партии...")
    batch_id = registry.create_production_batch(
        batch_name="Gateway_Batch_2024_Q1",
        device_count=50,
        device_type="gateway",
        tags=["production", "gateway", "farm"],
        target_deployment="production",
        hardware_specs={
            "cpu": "ARM64",
            "ram": "4GB",
            "storage": "32GB",
            "connectivity": ["WiFi", "Ethernet", "4G"],
        },
        created_by="production_manager",
        notes="Партия для развертывания на фермах Q1 2024",
    )
    print(f"Создана партия: {batch_id}")

    # Подготовка устройств в партии
    print("\n2. Подготовка устройств в партии...")
    devices = registry.prepare_batch_devices(batch_id)
    print(f"Подготовлено {len(devices)} устройств")
    for i, device in enumerate(devices[:3]):  # Показываем первые 3
        print(f"  📱 {device['device_serial']}")
        print(f"     Auth Key: {device['auth_key'][:20]}...")
        print(f"     Activation Token: {device['activation_token'][:20]}...")

    # Симуляция активации в поле
    print("\n3. Симуляция активации в поле...")
    if devices:
        test_device = devices[0]
        hw_signature = {
            "mac_addresses": ["00:1B:44:11:3A:B7", "00:1B:44:11:3A:B8"],
            "cpu_serial": "ARM_CPU_123456789",
            "disk_serial": "DISK_987654321",
            "board_serial": "BOARD_ABC123",
        }

        activation_result = registry.activate_device_in_field(
            activation_token=test_device["activation_token"],
            hardware_signature=hw_signature,
            installer_id="installer_001",
        )
        print(f"Активация результат: {activation_result}")

        # Одобрение регистрации
        print("\n4. Одобрение регистрации...")
        success = registry.approve_production_registration(
            request_id=activation_result["registration_request_id"],
            approved_by="admin",
            tailscale_ip="100.64.1.15",
        )
        print(f"Регистрация одобрена: {success}")

    # Получение статистики
    print("\n5. Продакшен статистика:")
    stats = registry.get_production_stats()
    for key, value in stats.items():
        if key not in ["timestamp", "production_timestamp"]:
            print(f"  {key}: {value}")

    print("\n✅ Продакшен тест завершен")
