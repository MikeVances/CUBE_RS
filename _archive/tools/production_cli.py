#!/usr/bin/env python3
"""
Production CLI - Утилиты командной строки для продакшен развертывания
Массовые операции с устройствами, подготовка партий, мониторинг активации
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем путь к web_app для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))

from production_device_registry import get_production_registry

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_batch(args):
    """Создание новой производственной партии"""
    registry = get_production_registry()

    tags = args.tags.split(",") if args.tags else ["production"]

    hardware_specs = {}
    if args.hardware_specs:
        try:
            hardware_specs = json.loads(args.hardware_specs)
        except json.JSONDecodeError:
            print("❌ Ошибка: Неверный формат JSON для hardware_specs")
            return False

    try:
        batch_id = registry.create_production_batch(
            batch_name=args.name,
            device_count=args.count,
            device_type=args.device_type,
            tags=tags,
            target_deployment=args.deployment,
            hardware_specs=hardware_specs,
            created_by=args.created_by,
            notes=args.notes or "",
        )

        print("✅ Создана производственная партия:")
        print(f"   ID: {batch_id}")
        print(f"   Название: {args.name}")
        print(f"   Количество: {args.count} устройств")
        print(f"   Тип: {args.device_type}")
        print(f"   Развертывание: {args.deployment}")

        return True

    except Exception as e:
        print(f"❌ Ошибка создания партии: {e}")
        return False


def prepare_batch(args):
    """Подготовка устройств в партии"""
    registry = get_production_registry()

    try:
        devices = registry.prepare_batch_devices(args.batch_id)

        print(f"✅ Подготовлена партия {args.batch_id}:")
        print(f"   Количество устройств: {len(devices)}")

        # Сохраняем информацию в файл если указан
        if args.output:
            output_data = {
                "batch_id": args.batch_id,
                "prepared_time": datetime.now().isoformat(),
                "device_count": len(devices),
                "devices": [],
            }

            for device in devices:
                output_data["devices"].append(
                    {
                        "device_serial": device["device_serial"],
                        "auth_key": device["auth_key"],
                        "activation_token": device["activation_token"],
                        "hardware_id": device["hardware_id"],
                    }
                )

            # Сохраняем в JSON или CSV
            output_path = Path(args.output)
            if output_path.suffix.lower() == ".csv":
                with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                    fieldnames = [
                        "device_serial",
                        "auth_key",
                        "activation_token",
                        "hardware_id",
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for device in devices:
                        writer.writerow(device)
            else:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)

            print(f"   Данные сохранены в: {args.output}")

        # Показываем первые несколько устройств
        print("\n📱 Первые устройства:")
        for device in devices[: min(3, len(devices))]:
            print(f"   {device['device_serial']}:")
            print(f"     Auth Key: {device['auth_key'][:30]}...")
            print(f"     Activation Token: {device['activation_token'][:20]}...")

        if len(devices) > 3:
            print(f"   ... и еще {len(devices) - 3} устройств")

        return True

    except Exception as e:
        print(f"❌ Ошибка подготовки партии: {e}")
        return False


def list_batches(args):
    """Список производственных партий"""
    registry = get_production_registry()

    try:
        batches = registry.get_production_batches(status=args.status)

        if not batches:
            print("📦 Производственных партий не найдено")
            return True

        print(f"📦 Производственные партии ({len(batches)}):")
        print()

        for batch in batches:
            status_icon = {
                "created": "🟡",
                "prepared": "🟢",
                "deployed": "🔵",
                "completed": "✅",
            }.get(batch.status, "❓")

            print(f"{status_icon} {batch.batch_name}")
            print(f"   ID: {batch.batch_id}")
            print(f"   Статус: {batch.status}")
            print(f"   Устройств: {batch.device_count} ({batch.device_type})")
            print(f"   Создано: {batch.created_time} ({batch.created_by})")
            print(f"   Развертывание: {batch.target_deployment}")
            if batch.notes:
                print(f"   Заметки: {batch.notes}")
            print()

        return True

    except Exception as e:
        print(f"❌ Ошибка получения списка партий: {e}")
        return False


def show_batch(args):
    """Показать детали партии"""
    registry = get_production_registry()

    try:
        batches = registry.get_production_batches()
        batch = next((b for b in batches if b.batch_id == args.batch_id), None)

        if not batch:
            print(f"❌ Партия {args.batch_id} не найдена")
            return False

        # Информация о партии
        print(f"📦 Партия: {batch.batch_name}")
        print(f"   ID: {batch.batch_id}")
        print(f"   Статус: {batch.status}")
        print(f"   Тип устройств: {batch.device_type}")
        print(f"   Количество: {batch.device_count}")
        print(f"   Создано: {batch.created_time} ({batch.created_by})")
        print(f"   Развертывание: {batch.target_deployment}")
        print(f"   Теги: {', '.join(batch.tags)}")

        if batch.hardware_specs:
            print("   Характеристики железа:")
            for key, value in batch.hardware_specs.items():
                print(f"     {key}: {value}")

        if batch.notes:
            print(f"   Заметки: {batch.notes}")

        # Устройства в партии
        devices = registry.get_batch_devices(args.batch_id)
        if devices:
            print(f"\n📱 Устройства в партии ({len(devices)}):")

            # Статистика по статусам
            status_counts = {}
            for device in devices:
                status_counts[device.status] = status_counts.get(device.status, 0) + 1

            print("   Статистика:")
            for status, count in status_counts.items():
                status_icon = {
                    "prepared": "🟡",
                    "activated": "🟠",
                    "registered": "🟢",
                    "deployed": "✅",
                }.get(status, "❓")
                print(f"     {status_icon} {status}: {count}")

            if args.show_devices:
                print("\n   Список устройств:")
                for device in devices[: args.limit] if args.limit else devices:
                    status_icon = {
                        "prepared": "🟡",
                        "activated": "🟠",
                        "registered": "🟢",
                        "deployed": "✅",
                    }.get(device.status, "❓")

                    print(f"   {status_icon} {device.device_serial} ({device.status})")
                    if device.activated_time:
                        print(f"       Активирован: {device.activated_time}")

        return True

    except Exception as e:
        print(f"❌ Ошибка получения информации о партии: {e}")
        return False


def list_activations(args):
    """Список активаций устройств"""
    registry = get_production_registry()

    try:
        # Получаем запросы на регистрацию от активированных устройств
        pending_requests = registry.get_pending_registration_requests()

        # Фильтруем только активированные в поле устройства
        field_activations = []
        for request in pending_requests:
            device_info = request.device_info
            if device_info.get("activation_method") == "field_activation":
                field_activations.append(request)

        if not field_activations:
            print("🔄 Ожидающих одобрения полевых активаций не найдено")
            return True

        print(f"🔄 Ожидающие одобрения полевые активации ({len(field_activations)}):")
        print()

        for request in field_activations:
            device_info = request.device_info
            print(f"📱 {request.device_hostname}")
            print(f"   Request ID: {request.request_id}")
            print(f"   Тип: {request.device_type}")
            print(f"   Время активации: {request.requested_time}")
            print(f"   Активировано: {device_info.get('activated_by', 'unknown')}")
            if request.tailscale_ip:
                print(f"   Tailscale IP: {request.tailscale_ip}")

            # Информация о железе
            if "hardware_signature" in device_info:
                hw_sig = device_info["hardware_signature"]
                if "mac_addresses" in hw_sig:
                    print(f"   MAC адреса: {', '.join(hw_sig['mac_addresses'])}")
                if "cpu_serial" in hw_sig:
                    print(f"   CPU Serial: {hw_sig['cpu_serial']}")
            print()

        return True

    except Exception as e:
        print(f"❌ Ошибка получения списка активаций: {e}")
        return False


def approve_activation(args):
    """Одобрение активации устройства"""
    registry = get_production_registry()

    try:
        success = registry.approve_production_registration(
            request_id=args.request_id,
            approved_by=args.approved_by,
            tailscale_ip=args.tailscale_ip or "",
        )

        if success:
            print("✅ Активация одобрена:")
            print(f"   Request ID: {args.request_id}")
            print(f"   Одобрил: {args.approved_by}")
            if args.tailscale_ip:
                print(f"   Tailscale IP: {args.tailscale_ip}")
        else:
            print(f"❌ Не удалось одобрить активацию {args.request_id}")
            return False

        return True

    except Exception as e:
        print(f"❌ Ошибка одобрения активации: {e}")
        return False


def production_stats(args):
    """Статистика продакшен развертывания"""
    registry = get_production_registry()

    try:
        stats = registry.get_production_stats()

        print("📊 Статистика продакшен развертывания:")
        print()

        # Общая статистика устройств
        print("🔧 Общая статистика:")
        print(f"   Всего устройств: {stats.get('total_devices', 0)}")
        print(f"   Активных устройств: {stats.get('active_devices', 0)}")
        print(f"   Ожидающих запросов: {stats.get('pending_requests', 0)}")
        print(f"   Активных auth ключей: {stats.get('active_auth_keys', 0)}")

        # Статистика по типам устройств
        devices_by_type = stats.get("devices_by_type", {})
        if devices_by_type:
            print("\n📱 Устройства по типам:")
            for device_type, count in devices_by_type.items():
                print(f"   {device_type}: {count}")

        # Продакшен статистика
        print("\n🏭 Продакшен статистика:")
        print(f"   Всего партий: {stats.get('total_production_batches', 0)}")
        print(
            f"   Предподготовленных устройств: {stats.get('total_pre_shared_devices', 0)}"
        )
        print(
            f"   Проверенных привязок к железу: {stats.get('verified_hardware_bindings', 0)}"
        )

        # Статистика партий по статусам
        batches_by_status = stats.get("batches_by_status", {})
        if batches_by_status:
            print("\n📦 Партии по статусам:")
            for status, count in batches_by_status.items():
                status_icon = {
                    "created": "🟡",
                    "prepared": "🟢",
                    "deployed": "🔵",
                    "completed": "✅",
                }.get(status, "❓")
                print(f"   {status_icon} {status}: {count}")

        # Статистика предподготовленных устройств
        pre_devices_by_status = stats.get("pre_devices_by_status", {})
        if pre_devices_by_status:
            print("\n🔄 Предподготовленные устройства:")
            for status, count in pre_devices_by_status.items():
                status_icon = {
                    "prepared": "🟡",
                    "activated": "🟠",
                    "registered": "🟢",
                    "deployed": "✅",
                }.get(status, "❓")
                print(f"   {status_icon} {status}: {count}")

        print(f"\n⏰ Обновлено: {stats.get('production_timestamp', 'N/A')}")

        return True

    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return False


def export_batch(args):
    """Экспорт данных партии для развертывания"""
    registry = get_production_registry()

    try:
        # Получаем информацию о партии
        batches = registry.get_production_batches()
        batch = next((b for b in batches if b.batch_id == args.batch_id), None)

        if not batch:
            print(f"❌ Партия {args.batch_id} не найдена")
            return False

        # Получаем устройства партии
        devices = registry.get_batch_devices(args.batch_id)

        if not devices:
            print(f"❌ В партии {args.batch_id} нет устройств")
            return False

        # Подготавливаем данные для экспорта
        export_data = {
            "batch_info": {
                "batch_id": batch.batch_id,
                "batch_name": batch.batch_name,
                "device_count": batch.device_count,
                "device_type": batch.device_type,
                "created_time": batch.created_time,
                "status": batch.status,
                "tags": batch.tags,
                "hardware_specs": batch.hardware_specs,
            },
            "deployment_instructions": {
                "step_1": "Установите gateway на целевое железо",
                "step_2": "Запустите gateway с предустановленным auth_key",
                "step_3": "Выполните активацию с помощью activation_token",
                "step_4": "Дождитесь одобрения регистрации администратором",
            },
            "devices": [],
        }

        for device in devices:
            device_data = {
                "device_serial": device.device_serial,
                "activation_token": device.activation_token,
                "hardware_id": device.hardware_id,
                "status": device.status,
                "created_time": device.created_time,
            }

            if device.activated_time:
                device_data["activated_time"] = device.activated_time

            export_data["devices"].append(device_data)

        # Сохраняем в файл
        output_path = Path(args.output)

        if output_path.suffix.lower() == ".csv":
            # CSV экспорт - только базовые данные устройств
            with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "device_serial",
                    "activation_token",
                    "hardware_id",
                    "status",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for device in export_data["devices"]:
                    writer.writerow({k: device.get(k, "") for k in fieldnames})
        else:
            # JSON экспорт - полные данные
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

        print("✅ Данные партии экспортированы:")
        print(f"   Партия: {batch.batch_name}")
        print(f"   Устройств: {len(devices)}")
        print(f"   Файл: {args.output}")

        return True

    except Exception as e:
        print(f"❌ Ошибка экспорта партии: {e}")
        return False


def main():
    """Главная функция CLI"""
    parser = argparse.ArgumentParser(
        description="Production CLI - Управление продакшен развертыванием CUBE_RS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Создание новой партии
  python production_cli.py create-batch --name "Gateway_2024_Q1" --count 50 --device-type gateway

  # Подготовка устройств в партии
  python production_cli.py prepare-batch --batch-id batch_abc123 --output devices.json

  # Список всех партий
  python production_cli.py list-batches

  # Детали конкретной партии
  python production_cli.py show-batch --batch-id batch_abc123 --show-devices

  # Список ожидающих активаций
  python production_cli.py list-activations

  # Одобрение активации
  python production_cli.py approve-activation --request-id req_123 --approved-by admin

  # Статистика развертывания
  python production_cli.py stats

  # Экспорт данных партии
  python production_cli.py export-batch --batch-id batch_abc123 --output deployment_data.json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    # Создание партии
    create_parser = subparsers.add_parser(
        "create-batch", help="Создать новую производственную партию"
    )
    create_parser.add_argument("--name", required=True, help="Название партии")
    create_parser.add_argument(
        "--count", type=int, required=True, help="Количество устройств"
    )
    create_parser.add_argument(
        "--device-type", default="gateway", help="Тип устройств (default: gateway)"
    )
    create_parser.add_argument(
        "--deployment",
        default="production",
        help="Тип развертывания (default: production)",
    )
    create_parser.add_argument("--tags", help="Теги через запятую")
    create_parser.add_argument(
        "--hardware-specs", help="JSON с характеристиками железа"
    )
    create_parser.add_argument(
        "--created-by", default="production_cli", help="Создатель партии"
    )
    create_parser.add_argument("--notes", help="Дополнительные заметки")
    create_parser.set_defaults(func=create_batch)

    # Подготовка партии
    prepare_parser = subparsers.add_parser(
        "prepare-batch", help="Подготовить устройства в партии"
    )
    prepare_parser.add_argument("--batch-id", required=True, help="ID партии")
    prepare_parser.add_argument(
        "--output", help="Файл для сохранения данных (JSON или CSV)"
    )
    prepare_parser.set_defaults(func=prepare_batch)

    # Список партий
    list_parser = subparsers.add_parser(
        "list-batches", help="Список производственных партий"
    )
    list_parser.add_argument("--status", help="Фильтр по статусу")
    list_parser.set_defaults(func=list_batches)

    # Показать партию
    show_parser = subparsers.add_parser("show-batch", help="Показать детали партии")
    show_parser.add_argument("--batch-id", required=True, help="ID партии")
    show_parser.add_argument(
        "--show-devices", action="store_true", help="Показать список устройств"
    )
    show_parser.add_argument("--limit", type=int, help="Лимит устройств для показа")
    show_parser.set_defaults(func=show_batch)

    # Список активаций
    activations_parser = subparsers.add_parser(
        "list-activations", help="Список ожидающих активаций"
    )
    activations_parser.set_defaults(func=list_activations)

    # Одобрение активации
    approve_parser = subparsers.add_parser(
        "approve-activation", help="Одобрить активацию устройства"
    )
    approve_parser.add_argument(
        "--request-id", required=True, help="ID запроса на регистрацию"
    )
    approve_parser.add_argument(
        "--approved-by", default="production_admin", help="Кто одобряет"
    )
    approve_parser.add_argument("--tailscale-ip", help="Tailscale IP адрес устройства")
    approve_parser.set_defaults(func=approve_activation)

    # Статистика
    stats_parser = subparsers.add_parser(
        "stats", help="Статистика продакшен развертывания"
    )
    stats_parser.set_defaults(func=production_stats)

    # Экспорт партии
    export_parser = subparsers.add_parser(
        "export-batch", help="Экспортировать данные партии"
    )
    export_parser.add_argument("--batch-id", required=True, help="ID партии")
    export_parser.add_argument(
        "--output", required=True, help="Выходной файл (JSON или CSV)"
    )
    export_parser.set_defaults(func=export_batch)

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
        logger.exception("Критическая ошибка в production_cli")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
