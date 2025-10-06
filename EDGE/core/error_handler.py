#!/usr/bin/env python3
"""
Централизованная система обработки ошибок для CUBE_RS.
Обеспечивает единый подход к обработке исключений, логированию и восстановлению.
"""

import asyncio
import functools
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import logging
try:  # structlog is optional
    import structlog  # type: ignore
    _STRUCTLOG_AVAILABLE = True
except Exception:  # pragma: no cover
    structlog = None  # type: ignore
    _STRUCTLOG_AVAILABLE = False

    class _FallbackLogger:
        def __init__(self, name: str):
            self._logger = logging.getLogger(name)

        def _log(self, level: int, msg: str, **kwargs):
            if kwargs:
                kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
                msg = f"{msg} | {kv}"
            self._logger.log(level, msg)

        # Severity-level methods used by ErrorSeverity values
        def low(self, msg: str, **kwargs):
            self._log(logging.INFO, msg, **kwargs)

        def medium(self, msg: str, **kwargs):
            self._log(logging.WARNING, msg, **kwargs)

        def high(self, msg: str, **kwargs):
            self._log(logging.ERROR, msg, **kwargs)

        def critical(self, msg: str, **kwargs):
            self._log(logging.CRITICAL, msg, **kwargs)

        # Common convenience methods
        def error(self, msg: str, **kwargs):
            self._log(logging.ERROR, msg, **kwargs)

        def warning(self, msg: str, **kwargs):
            self._log(logging.WARNING, msg, **kwargs)

        def info(self, msg: str, **kwargs):
            self._log(logging.INFO, msg, **kwargs)

        def debug(self, msg: str, **kwargs):
            self._log(logging.DEBUG, msg, **kwargs)

    def _get_logger(name: str):
        return _FallbackLogger(name)
else:
    def _get_logger(name: str):  # type: ignore
        return structlog.get_logger(name)

from .types import DatabaseError, ModbusError, TelegramError


class ErrorSeverity(Enum):
    """Уровни серьезности ошибок."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Категории ошибок."""

    MODBUS = "modbus"
    DATABASE = "database"
    TELEGRAM = "telegram"
    API = "api"
    NETWORK = "network"
    SYSTEM = "system"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"


@dataclass
class ErrorContext:
    """Контекст ошибки для обогащенного логирования."""

    component: str
    operation: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    device_id: Optional[int] = None
    additional_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Запись об ошибке."""

    error_id: str
    timestamp: datetime
    exception: Exception
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    stack_trace: str
    resolved: bool = False
    retry_count: int = 0
    last_occurrence: datetime = field(default_factory=datetime.now)


class RetryStrategy:
    """Стратегия повторных попыток."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Вычисляет задержку для попытки."""
        if attempt <= 0:
            return 0

        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)), self.max_delay
        )

        if self.jitter:
            import random

            delay *= 0.5 + random.random() * 0.5  # Jitter ±25%

        return delay


class ErrorHandler:
    """Централизованный обработчик ошибок."""

    def __init__(self):
        self.logger = _get_logger("error_handler")
        self.error_records: dict[str, ErrorRecord] = {}
        self.error_counts: dict[str, int] = {}
        self.circuit_breakers: dict[str, dict[str, Any]] = {}

        # Конфигурация обработки по типам ошибок
        self.error_config = {
            ModbusError: {
                "severity": ErrorSeverity.HIGH,
                "category": ErrorCategory.MODBUS,
                "retry_strategy": RetryStrategy(max_attempts=3, base_delay=2.0),
                "circuit_breaker": True,
            },
            DatabaseError: {
                "severity": ErrorSeverity.CRITICAL,
                "category": ErrorCategory.DATABASE,
                "retry_strategy": RetryStrategy(max_attempts=5, base_delay=1.0),
                "circuit_breaker": True,
            },
            TelegramError: {
                "severity": ErrorSeverity.MEDIUM,
                "category": ErrorCategory.TELEGRAM,
                "retry_strategy": RetryStrategy(max_attempts=2, base_delay=5.0),
                "circuit_breaker": False,
            },
            ConnectionError: {
                "severity": ErrorSeverity.HIGH,
                "category": ErrorCategory.NETWORK,
                "retry_strategy": RetryStrategy(max_attempts=3, base_delay=3.0),
                "circuit_breaker": True,
            },
            ValueError: {
                "severity": ErrorSeverity.LOW,
                "category": ErrorCategory.VALIDATION,
                "retry_strategy": None,  # Не повторяем валидационные ошибки
                "circuit_breaker": False,
            },
            PermissionError: {
                "severity": ErrorSeverity.HIGH,
                "category": ErrorCategory.PERMISSION,
                "retry_strategy": None,
                "circuit_breaker": False,
            },
        }

    def handle_error(
        self, exception: Exception, context: ErrorContext, should_raise: bool = True
    ) -> Optional[ErrorRecord]:
        """Обработка ошибки с логированием и записью."""
        try:
            # Генерируем ID ошибки
            error_id = self._generate_error_id(exception, context)

            # Определяем конфигурацию для типа ошибки
            error_config = self._get_error_config(exception)

            # Создаем запись об ошибке
            error_record = ErrorRecord(
                error_id=error_id,
                timestamp=datetime.now(),
                exception=exception,
                severity=error_config["severity"],
                category=error_config["category"],
                context=context,
                stack_trace=traceback.format_exc(),
            )

            # Обновляем существующую запись или создаем новую
            if error_id in self.error_records:
                existing_record = self.error_records[error_id]
                existing_record.retry_count += 1
                existing_record.last_occurrence = datetime.now()
                error_record = existing_record
            else:
                self.error_records[error_id] = error_record

            # Увеличиваем счетчик ошибок
            error_key = f"{context.component}:{type(exception).__name__}"
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

            # Логируем ошибку
            self._log_error(error_record)

            # Проверяем circuit breaker
            if error_config.get("circuit_breaker"):
                self._update_circuit_breaker(context.component, exception)

            # Вызываем исключение если нужно
            if should_raise:
                raise exception

            return error_record

        except Exception as handler_error:
            # Если обработчик ошибок сам упал - логируем и продолжаем
            self.logger.error(
                "Error handler failed",
                handler_error=str(handler_error),
                original_error=str(exception),
            )
            if should_raise:
                raise exception
            return None

    def _generate_error_id(self, exception: Exception, context: ErrorContext) -> str:
        """Генерация уникального ID ошибки."""
        import hashlib

        # Создаем уникальный хэш на основе типа ошибки, компонента и операции
        error_signature = (
            f"{type(exception).__name__}:{context.component}:{context.operation}"
        )
        return hashlib.md5(error_signature.encode()).hexdigest()[:12]

    def _get_error_config(self, exception: Exception) -> dict[str, Any]:
        """Получение конфигурации для типа ошибки."""
        exception_type = type(exception)

        # Проверяем точное совпадение типа
        if exception_type in self.error_config:
            return self.error_config[exception_type]

        # Проверяем наследование
        for error_type, config in self.error_config.items():
            if isinstance(exception, error_type):
                return config

        # Конфигурация по умолчанию
        return {
            "severity": ErrorSeverity.MEDIUM,
            "category": ErrorCategory.SYSTEM,
            "retry_strategy": RetryStrategy(max_attempts=1),
            "circuit_breaker": False,
        }

    def _log_error(self, error_record: ErrorRecord):
        """Логирование ошибки."""
        log_method = getattr(
            self.logger, error_record.severity.value, self.logger.error
        )

        log_method(
            "Exception occurred",
            error_id=error_record.error_id,
            exception_type=type(error_record.exception).__name__,
            exception_message=str(error_record.exception),
            category=error_record.category.value,
            component=error_record.context.component,
            operation=error_record.context.operation,
            user_id=error_record.context.user_id,
            device_id=error_record.context.device_id,
            retry_count=error_record.retry_count,
            stack_trace=error_record.stack_trace
            if error_record.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
            else None,
            **error_record.context.additional_data,
        )

    def _update_circuit_breaker(self, component: str, exception: Exception):
        """Обновление состояния circuit breaker."""
        current_time = datetime.now()
        cb_key = f"{component}:{type(exception).__name__}"

        if cb_key not in self.circuit_breakers:
            self.circuit_breakers[cb_key] = {
                "failures": 0,
                "last_failure": None,
                "state": "closed",  # closed, open, half-open
                "next_attempt": None,
            }

        cb_state = self.circuit_breakers[cb_key]
        cb_state["failures"] += 1
        cb_state["last_failure"] = current_time

        # Открываем circuit breaker после 5 ошибок
        if cb_state["failures"] >= 5 and cb_state["state"] == "closed":
            cb_state["state"] = "open"
            cb_state["next_attempt"] = current_time + timedelta(minutes=5)

            self.logger.warning(
                "Circuit breaker opened",
                component=component,
                exception_type=type(exception).__name__,
                failure_count=cb_state["failures"],
            )

    def is_circuit_breaker_open(
        self, component: str, exception_type: type[Exception]
    ) -> bool:
        """Проверка состояния circuit breaker."""
        cb_key = f"{component}:{exception_type.__name__}"
        cb_state = self.circuit_breakers.get(cb_key)

        if not cb_state or cb_state["state"] == "closed":
            return False

        if cb_state["state"] == "open":
            current_time = datetime.now()
            if current_time >= cb_state["next_attempt"]:
                # Переводим в half-open состояние
                cb_state["state"] = "half-open"
                self.logger.info(
                    "Circuit breaker half-open",
                    component=component,
                    exception_type=exception_type.__name__,
                )
                return False
            return True

        return False

    def reset_circuit_breaker(self, component: str, exception_type: type[Exception]):
        """Сброс circuit breaker после успешной операции."""
        cb_key = f"{component}:{exception_type.__name__}"
        if cb_key in self.circuit_breakers:
            cb_state = self.circuit_breakers[cb_key]
            if cb_state["state"] in ["open", "half-open"]:
                cb_state["state"] = "closed"
                cb_state["failures"] = 0
                self.logger.info(
                    "Circuit breaker reset",
                    component=component,
                    exception_type=exception_type.__name__,
                )

    async def retry_with_backoff(
        self,
        func: Callable,
        context: ErrorContext,
        retry_strategy: Optional[RetryStrategy] = None,
        *args,
        **kwargs,
    ) -> Any:
        """Выполнение функции с повторными попытками."""
        if retry_strategy is None:
            retry_strategy = RetryStrategy()

        last_exception = None

        for attempt in range(retry_strategy.max_attempts):
            try:
                # Проверяем circuit breaker
                if attempt > 0:  # Не проверяем на первой попытке
                    for error_type in self.error_config.keys():
                        if self.is_circuit_breaker_open(context.component, error_type):
                            raise ConnectionError(
                                f"Circuit breaker is open for {context.component}"
                            )

                # Выполняем функцию
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Сбрасываем circuit breaker при успехе
                if attempt > 0:
                    for error_type in self.error_config.keys():
                        self.reset_circuit_breaker(context.component, error_type)

                return result

            except Exception as e:
                last_exception = e

                # Не повторяем для определенных типов ошибок
                error_config = self._get_error_config(e)
                if error_config.get("retry_strategy") is None:
                    raise e

                # Логируем попытку
                self.logger.warning(
                    "Operation failed, will retry",
                    attempt=attempt + 1,
                    max_attempts=retry_strategy.max_attempts,
                    component=context.component,
                    operation=context.operation,
                    exception=str(e),
                )

                # Последняя попытка - не ждем
                if attempt == retry_strategy.max_attempts - 1:
                    break

                # Ждем перед следующей попыткой
                delay = retry_strategy.get_delay(attempt + 1)
                if delay > 0:
                    await asyncio.sleep(delay)

        # Все попытки исчерпаны
        if last_exception:
            self.handle_error(last_exception, context)

        raise last_exception or RuntimeError("All retry attempts failed")

    def get_error_statistics(self) -> dict[str, Any]:
        """Получение статистики ошибок."""
        current_time = datetime.now()
        recent_errors = [
            record
            for record in self.error_records.values()
            if (current_time - record.last_occurrence).total_seconds()
            < 3600  # За последний час
        ]

        return {
            "total_errors": len(self.error_records),
            "recent_errors": len(recent_errors),
            "error_counts": self.error_counts.copy(),
            "circuit_breakers": {
                key: {k: v for k, v in state.items() if k != "last_failure"}
                for key, state in self.circuit_breakers.items()
            },
            "errors_by_severity": {
                severity.value: sum(
                    1 for record in recent_errors if record.severity == severity
                )
                for severity in ErrorSeverity
            },
            "errors_by_category": {
                category.value: sum(
                    1 for record in recent_errors if record.category == category
                )
                for category in ErrorCategory
            },
        }


# Глобальный обработчик ошибок
error_handler = ErrorHandler()


def handle_errors(
    component: str,
    operation: str = "unknown",
    should_raise: bool = True,
    retry_strategy: Optional[RetryStrategy] = None,
):
    """Декоратор для обработки ошибок."""

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            context = ErrorContext(
                component=component, operation=operation or func.__name__
            )

            if retry_strategy:
                return await error_handler.retry_with_backoff(
                    func, context, retry_strategy, *args, **kwargs
                )
            else:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    error_handler.handle_error(e, context, should_raise)
                    return None

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            context = ErrorContext(
                component=component, operation=operation or func.__name__
            )

            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler.handle_error(e, context, should_raise)
                return None

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def log_and_ignore_errors(component: str, operation: str = "unknown"):
    """Декоратор для логирования ошибок без прерывания выполнения."""
    return handle_errors(component, operation, should_raise=False)


def retry_on_failure(
    component: str,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    operation: str = "unknown",
):
    """Декоратор для повторных попыток при ошибках."""
    retry_strategy = RetryStrategy(max_attempts=max_attempts, base_delay=base_delay)
    return handle_errors(component, operation, retry_strategy=retry_strategy)


async def safe_execute(
    func: Callable, context: ErrorContext, default_return: Any = None, *args, **kwargs
) -> Any:
    """Безопасное выполнение функции с обработкой ошибок."""
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    except Exception as e:
        error_handler.handle_error(e, context, should_raise=False)
        return default_return


def get_error_stats() -> dict[str, Any]:
    """Получение статистики ошибок."""
    return error_handler.get_error_statistics()
