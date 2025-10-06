#!/usr/bin/env python3
"""
Фильтр логов для предотвращения утечки секретов в системе КУБ-1063
Автоматически скрывает токены, ключи и другие конфиденциальные данные.
Поддерживает как обычное, так и структурированное логирование.
"""

import logging
import re
from typing import Any

try:
    import structlog  # type: ignore
    _STRUCTLOG_AVAILABLE = True
except Exception:  # pragma: no cover
    structlog = None  # type: ignore
    _STRUCTLOG_AVAILABLE = False


class SecurityLogFilter(logging.Filter):
    """Фильтр логов для защиты от утечки секретов"""

    # Паттерны для поиска секретов
    SECRET_PATTERNS = [
        # Telegram bot tokens (цифры:буквы_цифры_дефисы)
        (r"bot(\d+):([A-Za-z0-9_-]{35,})", r"bot\1:***"),
        # API ключи (длинные алфавитно-цифровые строки более 32 символов)
        (r"\b[A-Za-z0-9_-]{35,}\b", r"***"),
        # Пароли в URL
        (r"://([^:@\s]+):([^@\s]+)@", r"://\1:***@"),
        # JWT токены
        (r"Bearer\s+[A-Za-z0-9._-]{20,}", r"Bearer ***"),
        # Общие секреты в JSON
        (r'("(?:token|key|secret|password|passwd)"\s*:\s*")([^"]{8,})(")', r"\1***\3"),
    ]

    def filter(self, record):
        """Фильтрация записи лога"""
        if hasattr(record, "msg") and record.msg:
            original_msg = str(record.msg)
            filtered_msg = self._filter_secrets(original_msg)

            if filtered_msg != original_msg:
                record.msg = filtered_msg
                # Добавляем предупреждение о фильтрации
                if not hasattr(record, "_filtered"):
                    record._filtered = True

        # Также фильтруем args если есть
        if hasattr(record, "args") and record.args:
            filtered_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    filtered_args.append(self._filter_secrets(arg))
                else:
                    filtered_args.append(arg)
            record.args = tuple(filtered_args)

        return True

    def _filter_secrets(self, text: str) -> str:
        """Применение всех паттернов фильтрации к тексту"""
        filtered_text = text

        for pattern, replacement in self.SECRET_PATTERNS:
            try:
                filtered_text = re.sub(pattern, replacement, filtered_text)
            except Exception:
                # Если паттерн не сработал, продолжаем
                continue

        return filtered_text


def mask_secrets_processor(logger, method_name, event_dict):
    """Процессор для маскировки секретов в структурированных логах."""
    security_filter = SecurityLogFilter()

    # Фильтруем все строковые значения в event_dict
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = security_filter._filter_secrets(value)
        elif isinstance(value, dict):
            # Рекурсивно фильтруем вложенные словари
            event_dict[key] = _filter_dict_secrets(value, security_filter)
        elif isinstance(value, (list, tuple)):
            # Фильтруем списки и кортежи
            event_dict[key] = _filter_sequence_secrets(value, security_filter)

    return event_dict


def _filter_dict_secrets(
    data: dict[str, Any], filter_obj: SecurityLogFilter
) -> dict[str, Any]:
    """Рекурсивная фильтрация секретов в словарях."""
    filtered_dict = {}
    for key, value in data.items():
        if isinstance(value, str):
            filtered_dict[key] = filter_obj._filter_secrets(value)
        elif isinstance(value, dict):
            filtered_dict[key] = _filter_dict_secrets(value, filter_obj)
        elif isinstance(value, (list, tuple)):
            filtered_dict[key] = _filter_sequence_secrets(value, filter_obj)
        else:
            filtered_dict[key] = value
    return filtered_dict


def _filter_sequence_secrets(data, filter_obj: SecurityLogFilter):
    """Фильтрация секретов в списках и кортежах."""
    filtered_items = []
    for item in data:
        if isinstance(item, str):
            filtered_items.append(filter_obj._filter_secrets(item))
        elif isinstance(item, dict):
            filtered_items.append(_filter_dict_secrets(item, filter_obj))
        elif isinstance(item, (list, tuple)):
            filtered_items.append(_filter_sequence_secrets(item, filter_obj))
        else:
            filtered_items.append(item)

    return type(data)(filtered_items) if isinstance(data, tuple) else filtered_items


def setup_structured_logging():
    """Настройка структурированного логирования с маскировкой секретов.

    Если structlog недоступен, выполняется безопасный фолбэк на стандартный logging
    с установкой SecurityLogFilter. Это позволяет запускать систему даже без
    установленных dev‑зависимостей.
    """

    if not _STRUCTLOG_AVAILABLE:
        # Fallback: обычный logging с фильтром секретов
        logger = logging.getLogger("app")
        logger.setLevel(logging.INFO)
        setup_secure_logging()
        if not logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logger.addHandler(h)
        return logger

    structlog.configure(
        processors=[
            mask_secrets_processor,  # Первым делом маскируем секреты
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),  # Красивый вывод для разработки
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


def setup_structured_logging_production():
    """Настройка структурированного логирования для продакшена (JSON).

    Фолбэк на обычный logging, если structlog недоступен.
    """

    if not _STRUCTLOG_AVAILABLE:
        logger = logging.getLogger("app")
        logger.setLevel(logging.INFO)
        setup_secure_logging()
        if not logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logger.addHandler(h)
        return logger

    structlog.configure(
        processors=[
            mask_secrets_processor,  # Первым делом маскируем секреты
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),  # JSON для продакшена
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


def setup_secure_logging():
    """Настройка безопасного логирования для всего приложения"""
    # Добавляем фильтр ко всем существующим логгерам
    security_filter = SecurityLogFilter()

    # Критичные логгеры которые могут содержать токены
    critical_loggers = [
        "httpx",
        "telegram",
        "telegram.ext",
        "telegram.request",
        "urllib3.connectionpool",
        "requests",
        "aiohttp",
        "slowapi",
    ]

    for logger_name in critical_loggers:
        logger = logging.getLogger(logger_name)
        logger.addFilter(security_filter)
        # Устанавливаем уровень WARNING чтобы убрать DEBUG/INFO с токенами
        logger.setLevel(logging.WARNING)

    # Добавляем фильтр к корневому логгеру
    root_logger = logging.getLogger()
    root_logger.addFilter(security_filter)

    return security_filter


def get_secure_logger(name: str, use_structured: bool = True):
    """Получить безопасный логгер с маскировкой секретов."""
    if use_structured and _STRUCTLOG_AVAILABLE:
        # Настраиваем структурированное логирование если еще не настроено
        try:
            return structlog.get_logger(name)
        except Exception:
            # Fallback к обычному логированию
            pass

    # Обычное логирование с фильтром безопасности
    logger = logging.getLogger(name)
    security_filter = SecurityLogFilter()
    logger.addFilter(security_filter)
    return logger


if __name__ == "__main__":
    # Тест фильтра
    import logging

    # Настраиваем тестовое логирование
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Устанавливаем фильтр
    setup_secure_logging()

    logger = logging.getLogger("test")

    # Тестируем различные типы секретов
    test_cases = [
        "HTTP Request: POST https://api.telegram.org/bot<token>/getMe",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
        '{"api_key": "sk-1234567890abcdef1234567890abcdef"}',
        "postgresql://user:secret_password@localhost:5432/db",
        "Normal log message without secrets",
    ]

    print("🔍 Тестирование фильтра секретов:")
    filter_obj = SecurityLogFilter()

    for i, test_msg in enumerate(test_cases, 1):
        print(f"\n{i}. Исходное сообщение:")
        print(f"   {test_msg}")

        # Прямое тестирование фильтра
        filtered = filter_obj._filter_secrets(test_msg)
        print("   Отфильтрованное:")
        print(f"   {filtered}")

        if filtered != test_msg:
            print("   ✅ Секрет обнаружен и скрыт")
        else:
            print("   ℹ️  Секретов не найдено")
