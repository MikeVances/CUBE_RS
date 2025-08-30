#!/usr/bin/env python3
"""
Фильтр логов для предотвращения утечки секретов в системе КУБ-1063
Автоматически скрывает токены, ключи и другие конфиденциальные данные.
"""

import re
import logging

class SecurityLogFilter(logging.Filter):
    """Фильтр логов для защиты от утечки секретов"""
    
    # Паттерны для поиска секретов
    SECRET_PATTERNS = [
        # Telegram bot tokens (цифры:буквы_цифры_дефисы)
        (r'bot(\d+):([A-Za-z0-9_-]{35,})', r'bot\1:***'),
        # API ключи (длинные алфавитно-цифровые строки более 32 символов)
        (r'\b[A-Za-z0-9_-]{35,}\b', r'***'),
        # Пароли в URL
        (r'://([^:@\s]+):([^@\s]+)@', r'://\1:***@'),
        # JWT токены
        (r'Bearer\s+[A-Za-z0-9._-]{20,}', r'Bearer ***'),
        # Общие секреты в JSON
        (r'("(?:token|key|secret|password|passwd)"\s*:\s*")([^"]{8,})(")', r'\1***\3'),
    ]
    
    def filter(self, record):
        """Фильтрация записи лога"""
        if hasattr(record, 'msg') and record.msg:
            original_msg = str(record.msg)
            filtered_msg = self._filter_secrets(original_msg)
            
            if filtered_msg != original_msg:
                record.msg = filtered_msg
                # Добавляем предупреждение о фильтрации
                if not hasattr(record, '_filtered'):
                    record._filtered = True
        
        # Также фильтруем args если есть
        if hasattr(record, 'args') and record.args:
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

def setup_secure_logging():
    """Настройка безопасного логирования для всего приложения"""
    # Добавляем фильтр ко всем существующим логгерам
    security_filter = SecurityLogFilter()
    
    # Критичные логгеры которые могут содержать токены
    critical_loggers = [
        'httpx',
        'telegram',
        'telegram.ext',
        'telegram.request',
        'urllib3.connectionpool',
        'requests',
        'aiohttp'
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

if __name__ == "__main__":
    # Тест фильтра
    import logging
    
    # Настраиваем тестовое логирование
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    # Устанавливаем фильтр
    setup_secure_logging()
    
    logger = logging.getLogger('test')
    
    # Тестируем различные типы секретов
    test_cases = [
        "HTTP Request: POST https://api.telegram.org/bot8353463434:AAETfkpKjr1Y9PE7z1VKnpxFFPkTAtRKTQs/getMe",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
        '{"api_key": "sk-1234567890abcdef1234567890abcdef"}',
        "postgresql://user:secret_password@localhost:5432/db",
        "Normal log message without secrets"
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