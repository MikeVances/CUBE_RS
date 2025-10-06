#!/usr/bin/env python3
"""
Resilient Tunnel Broker - улучшенный брокер с управлением состоянием соединений
и автоматической очисткой
Ported from archive to EDGE for P2P device communication
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

# Import EDGE core components
try:
    from ..core.error_handler import ErrorHandler
    from ..core.health_checker import HealthChecker
    from ..core.log_filter import get_secure_logger
    logger = get_secure_logger(__name__)
except ImportError:
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

        # Initialize error handler
        try:
            self.error_handler = ErrorHandler()
        except:
            self.error_handler = None

    async def start(self):
        """Запуск менеджера состояний"""
        self.is_running = True
        logger.info("🔧 Connection State Manager запущен")

        # Инициализация БД
        await self.init_database()

        # Восстанавливаем состояния из БД
        await self.restore_connections_from_db()

        # Запускаем очистку в фоне
        asyncio.create_task(self.cleanup_loop())

    def stop(self):
        """Остановка менеджера"""
        self.is_running = False
        logger.info("🔧 Connection State Manager остановлен")

    async def init_database(self):
        """Инициализация базы данных для состояний соединений"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS connection_requests (
                        request_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        farm_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        app_offer TEXT NOT NULL,
                        farm_answer TEXT,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        last_activity REAL NOT NULL,
                        error_count INTEGER DEFAULT 0
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            if self.error_handler:
                await self.error_handler.handle_error(e, context="database_init")

    async def restore_connections_from_db(self):
        """Восстановление состояний соединений из БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT request_id, user_id, farm_id, app_offer, farm_answer,
                           created_at, status, expires_at, last_activity, error_count
                    FROM connection_requests
                    WHERE status IN ('pending', 'answered') AND expires_at > ?
                """,
                    (time.time(),),
                )
                
                rows = cursor.fetchall()
                restored_count = 0
                
                for row in rows:
                    request_id, user_id, farm_id, app_offer_json, farm_answer_json, created_at, status, expires_at, last_activity, error_count = row
                    
                    try:
                        app_offer = json.loads(app_offer_json)
                        farm_answer = json.loads(farm_answer_json) if farm_answer_json else None
                        
                        connection_state = ConnectionState(
                            request_id=request_id,
                            user_id=user_id,
                            farm_id=farm_id,
                            status=status,
                            created_at=created_at,
                            last_activity=last_activity,
                            app_offer=app_offer,
                            farm_answer=farm_answer,
                            error_count=error_count
                        )
                        
                        self.active_connections[request_id] = connection_state
                        self._update_connection_indices(connection_state)
                        restored_count += 1
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось восстановить соединение {request_id}: {e}")
                        continue
                        
                logger.info(f"🔄 Восстановлено {restored_count} активных соединений")
                
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления соединений: {e}")
            if self.error_handler:
                await self.error_handler.handle_error(e, context="restore_connections")

    def _update_connection_indices(self, connection_state: ConnectionState):
        """Обновление индексов соединений"""
        request_id = connection_state.request_id
        farm_id = connection_state.farm_id
        user_id = connection_state.user_id
        
        # Обновляем индекс ферм
        if farm_id not in self.farm_connections:
            self.farm_connections[farm_id] = set()
        self.farm_connections[farm_id].add(request_id)
        
        # Обновляем индекс пользователей
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(request_id)

    async def cleanup_loop(self):
        """Цикл автоматической очистки устаревших соединений"""
        while self.is_running:
            try:
                await self.cleanup_expired_connections()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле очистки: {e}")
                await asyncio.sleep(30)

    async def cleanup_expired_connections(self):
        """Очистка устаревших соединений"""
        current_time = time.time()
        expired_requests = []
        
        for request_id, conn_state in self.active_connections.items():
            # Проверяем таймаут установки соединения
            if conn_state.status == 'pending' and (current_time - conn_state.created_at) > self.connection_timeout:
                expired_requests.append(request_id)
                logger.info(f"⏱️ Соединение {request_id} истекло (таймаут установки)")
                
            # Проверяем таймаут неактивности
            elif (current_time - conn_state.last_activity) > self.idle_timeout:
                expired_requests.append(request_id)
                logger.info(f"⏱️ Соединение {request_id} истекло (неактивность)")
        
        # Удаляем истекшие соединения
        for request_id in expired_requests:
            await self.remove_connection(request_id, reason="expired")

    async def add_connection(self, connection_state: ConnectionState) -> bool:
        """Добавление нового соединения"""
        try:
            request_id = connection_state.request_id
            
            # Проверяем лимиты соединений
            if not await self._check_connection_limits(connection_state):
                return False
            
            # Сохраняем в память
            self.active_connections[request_id] = connection_state
            self._update_connection_indices(connection_state)
            
            # Сохраняем в БД
            await self._save_connection_to_db(connection_state)
            
            logger.info(f"✅ Соединение {request_id} добавлено (ферма: {connection_state.farm_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления соединения: {e}")
            if self.error_handler:
                await self.error_handler.handle_error(e, context="add_connection")
            return False

    async def _check_connection_limits(self, connection_state: ConnectionState) -> bool:
        """Проверка лимитов соединений"""
        farm_id = connection_state.farm_id
        user_id = connection_state.user_id
        
        # Лимит соединений на ферму (максимум 10)
        farm_connections_count = len(self.farm_connections.get(farm_id, set()))
        if farm_connections_count >= 10:
            logger.warning(f"⚠️ Превышен лимит соединений для фермы {farm_id}")
            return False
        
        # Лимит соединений на пользователя (максимум 5)
        user_connections_count = len(self.user_connections.get(user_id, set()))
        if user_connections_count >= 5:
            logger.warning(f"⚠️ Превышен лимит соединений для пользователя {user_id}")
            return False
        
        return True

    async def _save_connection_to_db(self, connection_state: ConnectionState):
        """Сохранение состояния соединения в БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO connection_requests
                    (request_id, user_id, farm_id, status, app_offer, farm_answer,
                     created_at, expires_at, last_activity, error_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        connection_state.request_id,
                        connection_state.user_id,
                        connection_state.farm_id,
                        connection_state.status,
                        json.dumps(connection_state.app_offer),
                        json.dumps(connection_state.farm_answer) if connection_state.farm_answer else None,
                        connection_state.created_at,
                        connection_state.created_at + self.connection_timeout,
                        connection_state.last_activity,
                        connection_state.error_count
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения соединения в БД: {e}")
            raise

    async def remove_connection(self, request_id: str, reason: str = "manual"):
        """Удаление соединения"""
        try:
            if request_id not in self.active_connections:
                return False
            
            connection_state = self.active_connections[request_id]
            farm_id = connection_state.farm_id
            user_id = connection_state.user_id
            
            # Удаляем из памяти
            del self.active_connections[request_id]
            
            # Обновляем индексы
            if farm_id in self.farm_connections:
                self.farm_connections[farm_id].discard(request_id)
                if not self.farm_connections[farm_id]:
                    del self.farm_connections[farm_id]
            
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(request_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
            
            # Удаляем из БД
            await self._remove_connection_from_db(request_id)
            
            logger.info(f"🗑️ Соединение {request_id} удалено (причина: {reason})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления соединения: {e}")
            if self.error_handler:
                await self.error_handler.handle_error(e, context="remove_connection")
            return False

    async def _remove_connection_from_db(self, request_id: str):
        """Удаление соединения из БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM connection_requests WHERE request_id = ?", (request_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка удаления соединения из БД: {e}")
            raise

    async def update_connection_status(self, request_id: str, status: str, farm_answer: dict = None) -> bool:
        """Обновление статуса соединения"""
        try:
            if request_id not in self.active_connections:
                return False
            
            connection_state = self.active_connections[request_id]
            connection_state.status = status
            connection_state.last_activity = time.time()
            
            if farm_answer:
                connection_state.farm_answer = farm_answer
            
            # Обновляем в БД
            await self._save_connection_to_db(connection_state)
            
            logger.info(f"🔄 Соединение {request_id} обновлено (статус: {status})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления соединения: {e}")
            if self.error_handler:
                await self.error_handler.handle_error(e, context="update_connection")
            return False

    def get_connection(self, request_id: str) -> Optional[ConnectionState]:
        """Получение состояния соединения"""
        return self.active_connections.get(request_id)

    def get_farm_connections(self, farm_id: str) -> list[ConnectionState]:
        """Получение всех соединений фермы"""
        request_ids = self.farm_connections.get(farm_id, set())
        return [self.active_connections[rid] for rid in request_ids if rid in self.active_connections]

    def get_user_connections(self, user_id: str) -> list[ConnectionState]:
        """Получение всех соединений пользователя"""
        request_ids = self.user_connections.get(user_id, set())
        return [self.active_connections[rid] for rid in request_ids if rid in self.active_connections]

    def get_statistics(self) -> dict:
        """Получение статистики соединений"""
        stats = {
            "total_connections": len(self.active_connections),
            "by_status": {},
            "by_farm": {},
            "by_user": {},
        }
        
        for conn_state in self.active_connections.values():
            # Статистика по статусам
            status = conn_state.status
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # Статистика по фермам
            farm_id = conn_state.farm_id
            stats["by_farm"][farm_id] = stats["by_farm"].get(farm_id, 0) + 1
            
            # Статистика по пользователям
            user_id = conn_state.user_id
            stats["by_user"][user_id] = stats["by_user"].get(user_id, 0) + 1
        
        return stats


class FarmStatusMonitor:
    """Мониторинг статуса ферм"""

    def __init__(self):
        self.farm_status: dict[str, dict] = {}
        self.heartbeat_timeout = 300  # 5 минут
        self.is_running = False

    async def start(self):
        """Запуск мониторинга"""
        self.is_running = True
        logger.info("📡 Farm Status Monitor запущен")
        asyncio.create_task(self.monitor_loop())

    def stop(self):
        """Остановка мониторинга"""
        self.is_running = False
        logger.info("📡 Farm Status Monitor остановлен")

    async def monitor_loop(self):
        """Цикл мониторинга статуса ферм"""
        while self.is_running:
            try:
                current_time = time.time()
                offline_farms = []
                
                for farm_id, status_info in self.farm_status.items():
                    last_heartbeat = status_info.get("last_heartbeat", 0)
                    if (current_time - last_heartbeat) > self.heartbeat_timeout:
                        if status_info.get("status") == "online":
                            offline_farms.append(farm_id)
                
                # Отмечаем фермы как offline
                for farm_id in offline_farms:
                    self.farm_status[farm_id]["status"] = "offline"
                    logger.warning(f"📡 Ферма {farm_id} перешла в статус offline")
                
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге ферм: {e}")
                await asyncio.sleep(30)

    def update_farm_status(self, farm_id: str, status: str = "online", metadata: dict = None):
        """Обновление статуса фермы"""
        current_time = time.time()
        
        if farm_id not in self.farm_status:
            self.farm_status[farm_id] = {}
        
        self.farm_status[farm_id].update({
            "status": status,
            "last_heartbeat": current_time,
            "last_update": current_time,
            "metadata": metadata or {},
        })
        
        logger.debug(f"📡 Обновлен статус фермы {farm_id}: {status}")

    def get_farm_status(self, farm_id: str) -> dict:
        """Получение статуса фермы"""
        return self.farm_status.get(farm_id, {"status": "unknown"})

    def get_online_farms(self) -> list[str]:
        """Получение списка онлайн ферм"""
        return [
            farm_id for farm_id, status_info in self.farm_status.items()
            if status_info.get("status") == "online"
        ]

    def get_all_farms_status(self) -> dict:
        """Получение статуса всех ферм"""
        return self.farm_status.copy()


class ResilientTunnelBroker:
    """Улучшенный Tunnel Broker с управлением состоянием"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8888, db_path: str = "tunnel_broker.db"):
        self.host = host
        self.port = port
        self.db_path = db_path
        
        # Компоненты системы
        self.connection_manager = ConnectionStateManager(db_path)
        self.farm_monitor = FarmStatusMonitor()
        
        # Flask приложение
        self.app = Flask(__name__)
        CORS(self.app, origins=["*"], allow_headers=["*"], methods=["*"])
        self.setup_routes()
        
        # Интеграция с EDGE компонентами
        try:
            self.health_checker = HealthChecker()
        except:
            self.health_checker = None
            
        self.is_running = False
        
        logger.info(f"🌐 Resilient Tunnel Broker инициализирован на {host}:{port}")

    def setup_routes(self):
        """Настройка маршрутов Flask"""
        
        @self.app.route("/health")
        def health():
            """Health check endpoint"""
            return jsonify({
                "status": "ok",
                "service": "resilient-tunnel-broker",
                "uptime": time.time() - getattr(self, 'start_time', time.time()),
                "active_connections": len(self.connection_manager.active_connections),
                "online_farms": len(self.farm_monitor.get_online_farms()),
            })

        @self.app.route("/api/request-connection", methods=["POST"])
        async def request_connection():
            """Запрос на установление P2P соединения"""
            try:
                data = request.get_json()
                
                # Валидация данных
                required_fields = ["user_id", "farm_id", "app_offer"]
                for field in required_fields:
                    if field not in data:
                        return jsonify({"error": f"Отсутствует поле {field}"}), 400
                
                # Проверяем, что ферма онлайн
                farm_status = self.farm_monitor.get_farm_status(data["farm_id"])
                if farm_status.get("status") != "online":
                    return jsonify({"error": "Ферма недоступна"}), 503
                
                # Создаем состояние соединения
                request_id = secrets.token_urlsafe(16)
                connection_state = ConnectionState(
                    request_id=request_id,
                    user_id=data["user_id"],
                    farm_id=data["farm_id"],
                    status="pending",
                    created_at=time.time(),
                    last_activity=time.time(),
                    app_offer=data["app_offer"]
                )
                
                # Добавляем соединение
                success = await self.connection_manager.add_connection(connection_state)
                if not success:
                    return jsonify({"error": "Не удалось создать соединение"}), 500
                
                logger.info(f"🔄 Запрос соединения {request_id}: {data['user_id']} → {data['farm_id']}")
                
                return jsonify({
                    "status": "success",
                    "request_id": request_id,
                    "message": "Запрос на соединение создан"
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка запроса соединения: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/get-pending-requests/<farm_id>", methods=["GET"])
        def get_pending_requests(farm_id):
            """Получение ожидающих запросов для фермы"""
            try:
                farm_connections = self.connection_manager.get_farm_connections(farm_id)
                pending_requests = [
                    {
                        "request_id": conn.request_id,
                        "user_id": conn.user_id,
                        "app_offer": conn.app_offer,
                        "created_at": conn.created_at
                    }
                    for conn in farm_connections if conn.status == "pending"
                ]
                
                # Обновляем статус фермы
                self.farm_monitor.update_farm_status(farm_id)
                
                return jsonify({
                    "status": "success",
                    "requests": pending_requests
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения запросов: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/answer-request", methods=["POST"])
        async def answer_request():
            """Ответ фермы на запрос соединения"""
            try:
                data = request.get_json()
                
                required_fields = ["request_id", "farm_answer"]
                for field in required_fields:
                    if field not in data:
                        return jsonify({"error": f"Отсутствует поле {field}"}), 400
                
                request_id = data["request_id"]
                
                # Обновляем состояние соединения
                success = await self.connection_manager.update_connection_status(
                    request_id, "answered", data["farm_answer"]
                )
                
                if not success:
                    return jsonify({"error": "Запрос не найден или истек"}), 404
                
                logger.info(f"✅ Получен ответ на запрос {request_id}")
                
                return jsonify({
                    "status": "success",
                    "message": "Ответ обработан"
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки ответа: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/get-answer/<request_id>", methods=["GET"])
        def get_answer(request_id):
            """Получение ответа фермы на запрос"""
            try:
                connection_state = self.connection_manager.get_connection(request_id)
                
                if not connection_state:
                    return jsonify({"error": "Запрос не найден"}), 404
                
                if connection_state.status == "pending":
                    return jsonify({
                        "status": "pending",
                        "message": "Ферма еще не ответила"
                    })
                
                elif connection_state.status == "answered":
                    return jsonify({
                        "status": "answered",
                        "farm_answer": connection_state.farm_answer
                    })
                
                else:
                    return jsonify({
                        "status": connection_state.status,
                        "message": f"Соединение в статусе {connection_state.status}"
                    })
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения ответа: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/connection-complete", methods=["POST"])
        async def connection_complete():
            """Завершение установления соединения"""
            try:
                data = request.get_json()
                request_id = data.get("request_id")
                success = data.get("success", False)
                
                if not request_id:
                    return jsonify({"error": "Отсутствует request_id"}), 400
                
                if success:
                    await self.connection_manager.update_connection_status(request_id, "connected")
                    logger.info(f"✅ Соединение {request_id} успешно установлено")
                else:
                    await self.connection_manager.update_connection_status(request_id, "failed")
                    logger.info(f"❌ Соединение {request_id} не удалось установить")
                
                return jsonify({
                    "status": "success",
                    "message": "Статус соединения обновлен"
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка завершения соединения: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/disconnect", methods=["POST"])
        async def disconnect():
            """Разрыв соединения"""
            try:
                data = request.get_json()
                request_id = data.get("request_id")
                
                if not request_id:
                    return jsonify({"error": "Отсутствует request_id"}), 400
                
                success = await self.connection_manager.remove_connection(request_id, reason="user_disconnect")
                
                if success:
                    logger.info(f"🔌 Соединение {request_id} разорвано")
                    return jsonify({
                        "status": "success",
                        "message": "Соединение разорвано"
                    })
                else:
                    return jsonify({"error": "Соединение не найдено"}), 404
                
            except Exception as e:
                logger.error(f"❌ Ошибка разрыва соединения: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/statistics", methods=["GET"])
        def get_statistics():
            """Получение статистики брокера"""
            try:
                connection_stats = self.connection_manager.get_statistics()
                farm_stats = self.farm_monitor.get_all_farms_status()
                
                return jsonify({
                    "status": "success",
                    "data": {
                        "connections": connection_stats,
                        "farms": farm_stats,
                        "uptime": time.time() - getattr(self, 'start_time', time.time()),
                    }
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения статистики: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

        @self.app.route("/api/farm-heartbeat", methods=["POST"])
        def farm_heartbeat():
            """Heartbeat от фермы"""
            try:
                data = request.get_json()
                farm_id = data.get("farm_id")
                
                if not farm_id:
                    return jsonify({"error": "Отсутствует farm_id"}), 400
                
                metadata = data.get("metadata", {})
                self.farm_monitor.update_farm_status(farm_id, "online", metadata)
                
                return jsonify({
                    "status": "success",
                    "message": "Heartbeat принят"
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки heartbeat: {e}")
                return jsonify({"error": "Внутренняя ошибка сервера"}), 500

    async def start(self):
        """Запуск брокера"""
        try:
            self.start_time = time.time()
            self.is_running = True
            
            # Запускаем компоненты
            await self.connection_manager.start()
            await self.farm_monitor.start()
            
            logger.info(f"🚀 Resilient Tunnel Broker запущен на {self.host}:{self.port}")
            
            # Интеграция с health checker
            if self.health_checker:
                await self.health_checker.add_component(
                    "tunnel_broker", 
                    lambda: self._health_check()
                )
            
            # Запуск Flask в отдельном потоке
            def run_flask():
                self.app.run(host=self.host, port=self.port, debug=False, threaded=True)
            
            flask_thread = threading.Thread(target=run_flask, daemon=False)
            flask_thread.start()
            
            return flask_thread
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска брокера: {e}")
            raise

    async def stop(self):
        """Остановка брокера"""
        logger.info("🛑 Остановка Resilient Tunnel Broker...")
        
        self.is_running = False
        
        # Останавливаем компоненты
        self.connection_manager.stop()
        self.farm_monitor.stop()
        
        logger.info("✅ Resilient Tunnel Broker остановлен")

    async def _health_check(self) -> dict:
        """Проверка здоровья брокера"""
        try:
            stats = self.connection_manager.get_statistics()
            online_farms = len(self.farm_monitor.get_online_farms())
            
            return {
                "status": "healthy",
                "active_connections": stats["total_connections"],
                "online_farms": online_farms,
                "uptime": time.time() - getattr(self, 'start_time', time.time()),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Точка входа для запуска брокера
async def main():
    """Главная функция для запуска Resilient Tunnel Broker"""
    
    # Параметры запуска
    host = os.getenv("BROKER_HOST", "0.0.0.0")
    port = int(os.getenv("BROKER_PORT", "8888"))
    db_path = os.getenv("BROKER_DB_PATH", "tunnel_broker.db")
    
    # Создание и запуск брокера
    broker = ResilientTunnelBroker(host=host, port=port, db_path=db_path)
    
    try:
        flask_thread = await broker.start()
        
        logger.info("🌐 Брокер работает. Нажмите Ctrl+C для остановки")
        
        # Ожидание сигнала остановки
        while broker.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("👋 Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка брокера: {e}")
    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(main())
