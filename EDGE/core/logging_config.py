#!/usr/bin/env python3
"""
Централизованная конфигурация логирования для EDGE проекта
Все логи автоматически размещаются в правильных директориях
"""

import logging
import os
from pathlib import Path
from typing import Optional

from core.utils.paths import get_project_root


def setup_logging(
    log_filename: str,
    level: int = logging.INFO,
    format_str: Optional[str] = None,
    include_console: bool = True
) -> logging.Logger:
    """
    Настройка логирования с автоматическим размещением файлов
    
    Args:
        log_filename: Имя лог файла (без пути)
        level: Уровень логирования
        format_str: Формат сообщений (по умолчанию стандартный)
        include_console: Включить вывод в консоль
    
    Returns:
        Настроенный logger
    """
    if format_str is None:
        format_str = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    
    # Определяем путь к лог файлу через logs директорию
    project_root = get_project_root()
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    log_path = logs_dir / log_filename
    
    # Создаем handlers
    handlers = []
    
    # File handler
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(format_str))
    handlers.append(file_handler)
    
    # Console handler
    if include_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(format_str))
        handlers.append(console_handler)
    
    # Настройка основного логгера
    logger_name = Path(log_filename).stem  # filename without extension
    logger = logging.getLogger(logger_name)
    
    # Очищаем предыдущие handlers
    logger.handlers.clear()
    
    # Добавляем наши handlers
    for handler in handlers:
        logger.addHandler(handler)
    
    logger.setLevel(level)
    logger.propagate = False  # Избегаем дублирования в root logger
    
    return logger


def setup_basic_logging(log_filename: str, level: int = logging.INFO):
    """
    Настройка basicConfig для совместимости с существующим кодом
    
    Args:
        log_filename: Имя лог файла
        level: Уровень логирования
    """
    project_root = get_project_root()
    logs_dir = project_root / "logs" 
    logs_dir.mkdir(exist_ok=True)
    
    log_path = logs_dir / log_filename
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(str(log_path), encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True  # Перезаписываем предыдущую конфигурацию
    )


# Convenience функции для стандартных логгеров
def get_modbus_logger() -> logging.Logger:
    """Логгер для modbus операций"""
    return setup_logging("modbus.log")


def get_gateway_logger() -> logging.Logger:
    """Логгер для gateway операций"""
    return setup_logging("gateway.log")


def get_bot_logger() -> logging.Logger:
    """Логгер для telegram бота"""
    return setup_logging("telegram_bot.log")