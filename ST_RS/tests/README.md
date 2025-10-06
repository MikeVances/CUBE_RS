# Тесты протокола RS485

Этот каталог содержит тесты для протокола RS485 Stienen.

## Структура тестов

### `test_protocol.py`
Основные модульные тесты протокола:

- **TestStienenProtocol**: Тесты базовых компонентов протокола
  - `test_protocol_commands()` - проверка команд протокола
  - `test_bus_state()` - проверка состояний шины
  - `test_data_item()` - проверка элементов данных

- **TestDataItem**: Тесты для класса DataItem
  - `test_data_item_creation()` - создание элементов данных
  - `test_data_item_validation()` - валидация данных

- **TestRS485Protocol**: Основные тесты класса RS485Protocol
  - `test_constants()` - проверка констант протокола
  - `test_message_id_increment()` - инкремент ID сообщений
  - `test_build_packet()` - создание пакетов
  - `test_parse_header()` - парсинг заголовков
  - `test_parse_packet()` - парсинг полных пакетов
  - `test_verify_crc()` - проверка CRC
  - `test_decode_data_payload()` - декодирование данных
  - `test_encode_data_payload()` - кодирование данных
  - `test_create_identification_request()` - создание запросов идентификации
  - `test_create_get_data_request()` - создание запросов получения данных
  - `test_create_set_data_request()` - создание запросов установки данных
  - `test_get_command_name()` - получение имен команд
  - `test_is_valid_packet()` - проверка валидности пакетов
  - `test_parse_message_from_buffer()` - поиск сообщений в буфере

- **TestProtocolFunctions**: Тесты удобных функций
  - `test_parse_stienen_packet()` - функция парсинга пакетов
  - `test_verify_packet_crc()` - функция проверки CRC
  - `test_decode_payload()` - функция декодирования payload
  - `test_create_packet()` - функция создания пакетов

### `test_protocol_integration.py`
Интеграционные тесты протокола:

- **TestProtocolIntegration**: Полные циклы работы протокола
  - `test_full_identification_cycle()` - полный цикл идентификации
  - `test_full_data_exchange_cycle()` - полный цикл обмена данными
  - `test_set_data_cycle()` - цикл установки данных
  - `test_buffer_parsing_with_multiple_packets()` - парсинг буфера с несколькими пакетами
  - `test_error_handling()` - обработка ошибок
  - `test_data_types_encoding_decoding()` - кодирование/декодирование различных типов данных
  - `test_message_id_uniqueness()` - уникальность ID сообщений
  - `test_protocol_constants_consistency()` - консистентность констант

## Запуск тестов

### Запуск всех тестов
```bash
python -m pytest tests/ -v
```

### Запуск конкретного файла тестов
```bash
python -m pytest tests/test_protocol.py -v
python -m pytest tests/test_protocol_integration.py -v
```

### Запуск в демонстрационном режиме
```bash
python tests/test_protocol.py
python tests/test_protocol_integration.py
```

## Покрытие функциональности

Тесты покрывают следующие аспекты протокола:

### ✅ Базовые компоненты
- [x] Команды протокола (IDENTIFICATION_REQ, GET_DATA_REQ, SET_DATA_REQ, etc.)
- [x] Состояния шины (FREE, BUSY, ERROR, RESERVED)
- [x] Элементы данных (DataItem)
- [x] Константы протокола

### ✅ Создание пакетов
- [x] Создание заголовков
- [x] Вычисление CRC
- [x] Сборка полных пакетов
- [x] Создание запросов идентификации
- [x] Создание запросов получения данных
- [x] Создание запросов установки данных

### ✅ Парсинг пакетов
- [x] Парсинг заголовков
- [x] Парсинг полных пакетов
- [x] Проверка CRC заголовка и данных
- [x] Валидация пакетов
- [x] Поиск сообщений в буфере

### ✅ Кодирование/декодирование данных
- [x] Кодирование payload данных
- [x] Декодирование payload данных
- [x] Обработка различных типов данных
- [x] Little Endian кодирование (как в C#)

### ✅ Интеграционные сценарии
- [x] Полный цикл идентификации устройства
- [x] Полный цикл обмена данными
- [x] Цикл установки данных
- [x] Обработка ошибок
- [x] Парсинг буфера с мусором

### ✅ Обработка ошибок
- [x] Неполные данные
- [x] Неправильный стартовый байт
- [x] Неправильный CRC
- [x] Валидация пакетов

## Результаты тестирования

Все тесты проходят успешно:
- **25 модульных тестов** в `test_protocol.py`
- **8 интеграционных тестов** в `test_protocol_integration.py`
- **Общий результат: 33/33 тестов пройдено**

## Демонстрация работы

При запуске в демонстрационном режиме тесты показывают:

1. **Команды протокола**: IDENTIFICATION_REQ=2, GET_DATA_REQ=8, SET_DATA_REQ=10
2. **Состояния шины**: FREE=0, BUSY=1, ERROR=2
3. **Создание пакетов**: размер пакета, данные в hex формате
4. **Проверка CRC**: OK/FAIL для заголовка и данных
5. **Парсинг буфера**: количество найденных пакетов

## Совместимость

Тесты полностью совместимы с оригинальным C# кодом протокола Stienen и проверяют:
- Правильную структуру заголовков (12 байт)
- Корректное вычисление CRC16 (CrcCcitt)
- Little Endian кодирование данных (как в C# Write методах)
- Big Endian кодирование заголовков
- Все команды и состояния из оригинального протокола 