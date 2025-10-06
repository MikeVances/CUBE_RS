#!/usr/bin/env python3
"""
Resilient Tunnel Broker - улучшенный брокер с управлением состоянием соединений
и автоматической очисткой
"""

import asyncio
import json
import logging
import os
import secrets
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

# Основные классы из оригинального tunnel_broker.py
sys.path.insert(0, os.path.dirname(__file__))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ConnectionState:
    """Состояние P2P соединения"""

    request_id: str
    user_id: str
    farm_id: str
    status: str  # 'pending', 'establishing', 'connected', 'failed', 'expired'
    created_at: float
    last_activity: float
    app_offer: dict
    farm_answer: Optional[dict] = None
    connection_quality: dict = None
    error_count: int = 0

    def __post_init__(self):
        if self.connection_quality is None:
            self.connection_quality = {
                "latency": None,
                "packet_loss": None,
                "bandwidth": None,
                "last_check": None,
            }


class ConnectionStateManager:
    """Менеджер состояния P2P соединений"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.active_connections: dict[str, ConnectionState] = {}
        self.farm_connections: dict[str, set[str]] = {}  # farm_id -> set of request_ids
        self.user_connections: dict[str, set[str]] = {}  # user_id -> set of request_ids
        self.cleanup_interval = 60  # Очистка каждую минуту
        self.connection_timeout = 300  # 5 минут на установку соединения
        self.idle_timeout = 1800  # 30 минут неактивности
        self.is_running = False

    async def start(self):
        """Запуск менеджера состояний"""
        self.is_running = True
        logger.info("🔧 Connection State Manager запущен")

        # Восстанавливаем состояния из БД
        await self.restore_connections_from_db()

        # Запускаем очистку в фоне
        asyncio.create_task(self.cleanup_loop())

    def stop(self):
        """Остановка менеджера"""
        self.is_running = False
        logger.info("🔧 Connection State Manager остановлен")

    async def restore_connections_from_db(self):
        """Восстановление состояний соединений из БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT request_id, user_id, farm_id, app_offer, farm_answer,
                           created_at, status, expires_at
                    FROM connection_requests
                    WHERE status IN ('pending', 'answered') AND expires_at > ?
                """,
                    (time.time(),),
                )

                restored_count = 0
                for row in cursor.fetchall():
                    (
                        request_id,
                        user_id,
                        farm_id,
                        app_offer,
                        farm_answer,
                        created_at,
                        status,
                        expires_at,
                    ) = row

                    # Создаем состояние соединения
                    connection_state = ConnectionState(
                        request_id=request_id,
                        user_id=user_id,
                        farm_id=farm_id,
                        status=status,
                        created_at=created_at,
                        last_activity=time.time(),
                        app_offer=json.loads(app_offer) if app_offer else {},
                        farm_answer=json.loads(farm_answer) if farm_answer else None,
                    )

                    await self.register_connection(connection_state)
                    restored_count += 1

                logger.info(f"✅ Восстановлено {restored_count} активных соединений")

        except Exception as e:
            logger.error(f"Ошибка восстановления соединений: {e}")

    async def register_connection(self, connection_state: ConnectionState):
        """Регистрация нового соединения"""
        request_id = connection_state.request_id
        user_id = connection_state.user_id
        farm_id = connection_state.farm_id

        # Добавляем в активные соединения
        self.active_connections[request_id] = connection_state

        # Индексируем по ферме
        if farm_id not in self.farm_connections:
            self.farm_connections[farm_id] = set()
        self.farm_connections[farm_id].add(request_id)

        # Индексируем по пользователю
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(request_id)

        logger.debug(
            f"🔗 Зарегистрировано соединение {request_id}: {user_id} -> {farm_id}"
        )

    async def update_connection_status(
        self, request_id: str, status: str, farm_answer: dict = None
    ):
        """Обновление статуса соединения"""
        if request_id in self.active_connections:
            connection = self.active_connections[request_id]
            connection.status = status
            connection.last_activity = time.time()

            if farm_answer:
                connection.farm_answer = farm_answer

            # Обновляем в БД
            await self.save_connection_to_db(connection)

            logger.debug(f"🔄 Обновлен статус соединения {request_id}: {status}")

    async def update_connection_activity(
        self, request_id: str, quality_metrics: dict = None
    ):
        """Обновление активности соединения"""
        if request_id in self.active_connections:
            connection = self.active_connections[request_id]
            connection.last_activity = time.time()

            if quality_metrics:
                connection.connection_quality.update(quality_metrics)
                connection.connection_quality["last_check"] = time.time()

            logger.debug(f"📊 Обновлена активность соединения {request_id}")

    async def remove_connection(self, request_id: str):
        """Удаление соединения"""
        if request_id not in self.active_connections:
            return

        connection = self.active_connections[request_id]
        user_id = connection.user_id
        farm_id = connection.farm_id

        # Удаляем из индексов
        if farm_id in self.farm_connections:
            self.farm_connections[farm_id].discard(request_id)
            if not self.farm_connections[farm_id]:
                del self.farm_connections[farm_id]

        if user_id in self.user_connections:
            self.user_connections[user_id].discard(request_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Удаляем из активных
        del self.active_connections[request_id]

        # Удаляем из БД
        await self.remove_connection_from_db(request_id)

        logger.info(f"🗑️ Удалено соединение {request_id}")

    async def get_farm_connections(self, farm_id: str) -> list[ConnectionState]:
        """Получение всех соединений фермы"""
        if farm_id not in self.farm_connections:
            return []

        connections = []
        for request_id in self.farm_connections[farm_id]:
            if request_id in self.active_connections:
                connections.append(self.active_connections[request_id])

        return connections

    async def get_user_connections(self, user_id: str) -> list[ConnectionState]:
        """Получение всех соединений пользователя"""
        if user_id not in self.user_connections:
            return []

        connections = []
        for request_id in self.user_connections[user_id]:
            if request_id in self.active_connections:
                connections.append(self.active_connections[request_id])

        return connections

    async def cleanup_loop(self):
        """Цикл очистки устаревших соединений"""
        while self.is_running:
            try:
                await self.cleanup_expired_connections()
                await self.cleanup_idle_connections()
                await self.cleanup_failed_connections()

            except Exception as e:
                logger.error(f"Ошибка в cleanup loop: {e}")

            await asyncio.sleep(self.cleanup_interval)

    async def cleanup_expired_connections(self):
        """Очистка просроченных соединений"""
        current_time = time.time()
        expired_connections = []

        for request_id, connection in self.active_connections.items():
            # Соединения в статусе pending с истекшим временем
            if (
                connection.status == "pending"
                and current_time - connection.created_at > self.connection_timeout
            ):
                expired_connections.append(request_id)

        for request_id in expired_connections:
            connection = self.active_connections[request_id]
            logger.info(f"⏰ Соединение {request_id} просрочено (pending -> expired)")
            await self.update_connection_status(request_id, "expired")
            await self.remove_connection(request_id)

    async def cleanup_idle_connections(self):
        """Очистка неактивных соединений"""
        current_time = time.time()
        idle_connections = []

        for request_id, connection in self.active_connections.items():
            # Соединения без активности слишком долго
            if (
                connection.status == "connected"
                and current_time - connection.last_activity > self.idle_timeout
            ):
                idle_connections.append(request_id)

        for request_id in idle_connections:
            connection = self.active_connections[request_id]
            logger.info(f"💤 Соединение {request_id} неактивно (connected -> idle)")
            await self.remove_connection(request_id)

    async def cleanup_failed_connections(self):
        """Очистка соединений с множественными ошибками"""
        failed_connections = []

        for request_id, connection in self.active_connections.items():
            if connection.error_count >= 5:  # Более 5 ошибок
                failed_connections.append(request_id)

        for request_id in failed_connections:
            connection = self.active_connections[request_id]
            logger.info(f"❌ Соединение {request_id} имеет множественные ошибки")
            await self.update_connection_status(request_id, "failed")
            await self.remove_connection(request_id)

    async def save_connection_to_db(self, connection: ConnectionState):
        """Сохранение соединения в БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE connection_requests
                    SET status = ?, farm_answer = ?, last_activity = ?
                    WHERE request_id = ?
                """,
                    (
                        connection.status,
                        json.dumps(connection.farm_answer)
                        if connection.farm_answer
                        else None,
                        connection.last_activity,
                        connection.request_id,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения соединения {connection.request_id}: {e}")

    async def remove_connection_from_db(self, request_id: str):
        """Удаление соединения из БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM connection_requests WHERE request_id = ?",
                    (request_id,),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка удаления соединения {request_id}: {e}")

    def get_statistics(self) -> dict:
        """Получение статистики соединений"""
        stats = {
            "total_active": len(self.active_connections),
            "by_status": {},
            "by_farm": {},
            "avg_connection_age": 0,
            "quality_metrics": {"avg_latency": None, "connections_with_quality": 0},
        }

        # Статистика по статусам
        for connection in self.active_connections.values():
            status = connection.status
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        # Статистика по фермам
        for farm_id, request_ids in self.farm_connections.items():
            stats["by_farm"][farm_id] = len(request_ids)

        # Средний возраст соединений
        if self.active_connections:
            current_time = time.time()
            total_age = sum(
                current_time - conn.created_at
                for conn in self.active_connections.values()
            )
            stats["avg_connection_age"] = total_age / len(self.active_connections)

        # Качество соединений
        latencies = []
        quality_connections = 0

        for connection in self.active_connections.values():
            if connection.connection_quality.get("last_check"):
                quality_connections += 1
                if connection.connection_quality.get("latency"):
                    latencies.append(connection.connection_quality["latency"])

        stats["quality_metrics"]["connections_with_quality"] = quality_connections
        if latencies:
            stats["quality_metrics"]["avg_latency"] = sum(latencies) / len(latencies)

        return stats


class FarmStatusMonitor:
    """Мониторинг статуса ферм"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.farm_status = {}  # farm_id -> last_seen, status
        self.offline_threshold = 300  # 5 минут без heartbeat = офлайн
        self.is_running = False

    async def start(self):
        """Запуск мониторинга ферм"""
        self.is_running = True
        logger.info("📊 Farm Status Monitor запущен")

        # Загружаем текущие статусы
        await self.load_farm_statuses()

        # Запускаем мониторинг
        asyncio.create_task(self.monitor_loop())

    def stop(self):
        """Остановка мониторинга"""
        self.is_running = False

    async def load_farm_statuses(self):
        """Загрузка статусов ферм из БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT farm_id, last_seen, status FROM farms
                """
                )

                for farm_id, last_seen, status in cursor.fetchall():
                    self.farm_status[farm_id] = {
                        "last_seen": last_seen,
                        "status": status,
                    }

                logger.info(f"📊 Загружено статусов ферм: {len(self.farm_status)}")

        except Exception as e:
            logger.error(f"Ошибка загрузки статусов ферм: {e}")

    async def update_farm_heartbeat(self, farm_id: str):
        """Обновление heartbeat фермы"""
        current_time = time.time()

        self.farm_status[farm_id] = {"last_seen": current_time, "status": "online"}

        # Обновляем в БД
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE farms SET last_seen = ?, status = 'online'
                    WHERE farm_id = ?
                """,
                    (current_time, farm_id),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления heartbeat для {farm_id}: {e}")

    async def monitor_loop(self):
        """Цикл мониторинга статусов ферм"""
        while self.is_running:
            try:
                current_time = time.time()
                offline_farms = []

                for farm_id, info in self.farm_status.items():
                    if (
                        current_time - info["last_seen"] > self.offline_threshold
                        and info["status"] == "online"
                    ):
                        offline_farms.append(farm_id)

                # Помечаем фермы как offline
                for farm_id in offline_farms:
                    await self.mark_farm_offline(farm_id)

                if offline_farms:
                    logger.info(f"📴 Фермы перешли в offline: {offline_farms}")

            except Exception as e:
                logger.error(f"Ошибка в monitor loop: {e}")

            await asyncio.sleep(60)  # Проверка каждую минуту

    async def mark_farm_offline(self, farm_id: str):
        """Перевод фермы в статус offline"""
        self.farm_status[farm_id]["status"] = "offline"

        # Обновляем в БД
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE farms SET status = 'offline'
                    WHERE farm_id = ?
                """,
                    (farm_id,),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка пометки {farm_id} как offline: {e}")

    def get_online_farms(self) -> list[str]:
        """Получение списка онлайн ферм"""
        return [
            farm_id
            for farm_id, info in self.farm_status.items()
            if info["status"] == "online"
        ]


class ResilientTunnelBroker:
    """Улучшенный Tunnel Broker с устойчивостью и управлением состояниями"""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        db_path: str = "resilient_tunnel_broker.db",
    ):
        self.host = host
        self.port = port
        self.db_path = db_path

        # Инициализируем БД (копируем структуру из оригинального broker)
        self.init_database()

        # Компоненты устойчивости
        self.connection_manager = ConnectionStateManager(self.db_path)
        self.farm_monitor = FarmStatusMonitor(self.db_path)

        # Flask приложение
        self.app = Flask(__name__)
        CORS(self.app)
        self.setup_routes()

        # WebSocket клиенты
        self.ws_clients = {}
        self.setup_websocket()

        # Статистика брокера
        self.broker_stats = {
            "start_time": time.time(),
            "total_requests": 0,
            "successful_connections": 0,
            "failed_connections": 0,
        }

    def init_database(self):
        """Инициализация базы данных (расширенная версия)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Основные таблицы (копия из оригинального broker)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS farms (
                    farm_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    farm_name TEXT NOT NULL,
                    last_seen REAL NOT NULL,
                    local_ip TEXT NOT NULL,
                    public_ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    FOREIGN KEY (owner_id) REFERENCES users (user_id)
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_farms (
                    user_id TEXT NOT NULL,
                    farm_id TEXT NOT NULL,
                    access_level TEXT DEFAULT 'read',
                    granted_at REAL NOT NULL,
                    PRIMARY KEY (user_id, farm_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (farm_id) REFERENCES farms (farm_id)
                )
            """
            )

            # Расширенная таблица соединений
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS connection_requests (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    farm_id TEXT NOT NULL,
                    app_offer TEXT NOT NULL,
                    farm_answer TEXT,
                    created_at REAL NOT NULL,
                    last_activity REAL NOT NULL,
                    status TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    error_count INTEGER DEFAULT 0,
                    quality_metrics TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (farm_id) REFERENCES farms (farm_id)
                )
            """
            )

            # Таблица статистики
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS connection_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    farm_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    connection_duration REAL,
                    quality_avg TEXT,
                    disconnect_reason TEXT,
                    timestamp REAL NOT NULL
                )
            """
            )

            conn.commit()
            logger.info("✅ База данных Resilient Tunnel Broker инициализирована")

    def setup_routes(self):
        """Настройка расширенных HTTP маршрутов"""

        # Базовые маршруты (копия логики из оригинального broker)
        @self.app.route("/health")
        def health():
            stats = self.connection_manager.get_statistics()
            return jsonify(
                {
                    "status": "healthy",
                    "service": "resilient-tunnel-broker",
                    "timestamp": time.time(),
                    "uptime": time.time() - self.broker_stats["start_time"],
                    "connections": stats,
                    "online_farms": len(self.farm_monitor.get_online_farms()),
                }
            )

        @self.app.route("/api/farm/heartbeat", methods=["POST"])
        def farm_heartbeat():
            data = request.json
            farm_id = data.get("farm_id")

            if not farm_id:
                return jsonify({"status": "error", "message": "farm_id required"}), 400

            # Обновляем heartbeat
            asyncio.run_coroutine_threadsafe(
                self.farm_monitor.update_farm_heartbeat(farm_id),
                asyncio.get_event_loop(),
            )

            # Обновляем основную БД
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE farms SET last_seen = ?, public_ip = ?, status = 'online'
                    WHERE farm_id = ?
                """,
                    (time.time(), request.remote_addr, farm_id),
                )
                conn.commit()

            # Получаем pending запросы для фермы
            pending_requests = asyncio.run_coroutine_threadsafe(
                self.get_pending_requests_for_farm(farm_id), asyncio.get_event_loop()
            ).result()

            return jsonify(
                {
                    "status": "success",
                    "pending_requests": len(pending_requests),
                    "requests": pending_requests,
                }
            )

        @self.app.route("/api/connect/request", methods=["POST"])
        def request_connection():
            data = request.json

            user_id = data.get("user_id")
            farm_id = data.get("farm_id")
            app_offer = data.get("webrtc_offer", {})

            # Создаем запрос на соединение
            request_id = f"req_{secrets.token_hex(12)}"
            expires_at = time.time() + 300  # 5 минут

            try:
                # Сохраняем в БД
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO connection_requests (
                            request_id, user_id, farm_id, app_offer, created_at,
                            last_activity, status, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            request_id,
                            user_id,
                            farm_id,
                            json.dumps(app_offer),
                            time.time(),
                            time.time(),
                            "pending",
                            expires_at,
                        ),
                    )
                    conn.commit()

                # Создаем состояние соединения
                connection_state = ConnectionState(
                    request_id=request_id,
                    user_id=user_id,
                    farm_id=farm_id,
                    status="pending",
                    created_at=time.time(),
                    last_activity=time.time(),
                    app_offer=app_offer,
                )

                # Регистрируем в менеджере
                asyncio.run_coroutine_threadsafe(
                    self.connection_manager.register_connection(connection_state),
                    asyncio.get_event_loop(),
                )

                # Уведомляем ферму
                self.notify_farm(
                    farm_id,
                    {
                        "type": "connection_request",
                        "request_id": request_id,
                        "user_id": user_id,
                    },
                )

                self.broker_stats["total_requests"] += 1

                return jsonify(
                    {
                        "status": "success",
                        "request_id": request_id,
                        "message": "Запрос на соединение отправлен",
                    }
                )

            except Exception as e:
                logger.error(f"Ошибка создания запроса: {e}")
                return (
                    jsonify({"status": "error", "message": "Ошибка создания запроса"}),
                    400,
                )

        @self.app.route("/api/connect/answer", methods=["POST"])
        def answer_connection():
            data = request.json
            request_id = data.get("request_id")
            farm_answer = data.get("webrtc_answer")

            # Обновляем состояние соединения
            asyncio.run_coroutine_threadsafe(
                self.connection_manager.update_connection_status(
                    request_id, "answered", farm_answer
                ),
                asyncio.get_event_loop(),
            )

            return jsonify({"status": "success", "message": "Ответ сохранен"})

        @self.app.route("/api/connect/status/<request_id>")
        def get_connection_status(request_id):
            # Получаем состояние из менеджера
            if request_id in self.connection_manager.active_connections:
                connection = self.connection_manager.active_connections[request_id]

                return jsonify(
                    {
                        "status": "success",
                        "connection_status": connection.status,
                        "farm_answer": connection.farm_answer,
                        "quality": connection.connection_quality,
                        "created_at": connection.created_at,
                        "last_activity": connection.last_activity,
                    }
                )
            else:
                return jsonify({"status": "error", "message": "Запрос не найден"}), 404

        @self.app.route("/api/stats")
        def get_broker_stats():
            connection_stats = self.connection_manager.get_statistics()

            return jsonify(
                {
                    "broker": self.broker_stats,
                    "connections": connection_stats,
                    "farms": {
                        "online": self.farm_monitor.get_online_farms(),
                        "total_online": len(self.farm_monitor.get_online_farms()),
                    },
                }
            )

    async def get_pending_requests_for_farm(self, farm_id: str) -> list[dict]:
        """Получение ожидающих запросов для фермы"""
        connections = await self.connection_manager.get_farm_connections(farm_id)

        pending_requests = []
        for connection in connections:
            if connection.status == "pending":
                pending_requests.append(
                    {
                        "request_id": connection.request_id,
                        "user_id": connection.user_id,
                        "app_offer": connection.app_offer,
                        "created_at": connection.created_at,
                    }
                )

        return pending_requests

    def notify_farm(self, farm_id: str, message: dict):
        """Уведомление фермы через WebSocket"""
        if farm_id in self.ws_clients:
            try:
                client = self.ws_clients[farm_id]
                # В реальности: websocket_server.send_message(client, json.dumps(message))
                logger.info(
                    f"📨 Уведомление отправлено ферме {farm_id}: {message.get('type')}"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления ферме {farm_id}: {e}")

    def setup_websocket(self):
        """Настройка WebSocket сервера (упрощенная версия)"""
        # В реальной реализации здесь будет полноценный WebSocket сервер
        logger.info(f"🔌 WebSocket сервер настроен на порту {self.port + 1}")

    async def start(self):
        """Запуск resilient broker"""
        logger.info(f"🚀 Resilient Tunnel Broker запущен на {self.host}:{self.port}")

        # Запускаем компоненты устойчивости
        await self.connection_manager.start()
        await self.farm_monitor.start()

        # Запускаем Flask приложение в отдельном потоке
        flask_thread = threading.Thread(
            target=lambda: self.app.run(
                host=self.host, port=self.port, debug=False, threaded=True
            ),
            daemon=False,
        )
        flask_thread.start()

        logger.info("✅ Все компоненты Resilient Tunnel Broker запущены")

        # Основной цикл
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Остановка Resilient Tunnel Broker...")
            self.connection_manager.stop()
            self.farm_monitor.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resilient Tunnel Broker Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument(
        "--db", default="resilient_tunnel_broker.db", help="Database file path"
    )

    args = parser.parse_args()

    broker = ResilientTunnelBroker(host=args.host, port=args.port, db_path=args.db)

    try:
        asyncio.run(broker.start())
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
        pass
