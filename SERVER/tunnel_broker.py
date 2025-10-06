#!/usr/bin/env python3
"""
Tunnel Broker Server - центральный коммутатор для P2P соединений
Работает на сервере с белым IP, координирует подключения между фермами и приложениями
"""

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

import websocket_server
from flask import Flask, jsonify, request
from flask_cors import CORS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class FarmInfo:
    """Информация о ферме"""

    farm_id: str
    owner_id: str
    farm_name: str
    last_seen: float
    local_ip: str
    public_ip: str
    port: int
    status: str = "online"
    api_key: str = ""
    capabilities: list[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = ["kub1063", "monitoring"]


@dataclass
class UserInfo:
    """Информация о пользователе"""

    user_id: str
    username: str
    email: str
    password_hash: str
    farms: list[str] = None
    created_at: float = None

    def __post_init__(self):
        if self.farms is None:
            self.farms = []
        if self.created_at is None:
            self.created_at = time.time()


@dataclass
class ConnectionRequest:
    """Запрос на P2P соединение"""

    request_id: str
    user_id: str
    farm_id: str
    app_offer: dict
    created_at: float
    status: str = "pending"


class TunnelBrokerDB:
    """База данных для Tunnel Broker"""

    def __init__(self, db_path: str = "tunnel_broker.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Таблица пользователей
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

            # Таблица ферм
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

            # Таблица связей пользователь-ферма
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

            # Таблица P2P запросов
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS connection_requests (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    farm_id TEXT NOT NULL,
                    app_offer TEXT NOT NULL,
                    farm_answer TEXT,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (farm_id) REFERENCES farms (farm_id)
                )
            """
            )

            conn.commit()
            logger.info("✅ База данных Tunnel Broker инициализирована")

    def register_user(self, username: str, email: str, password: str) -> Optional[str]:
        """Регистрация нового пользователя"""
        try:
            user_id = f"user_{secrets.token_hex(8)}"
            password_hash = hashlib.sha256(password.encode()).hexdigest()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (user_id, username, email, password_hash, time.time()),
                )
                conn.commit()

            logger.info(f"✅ Пользователь {username} зарегистрирован: {user_id}")
            return user_id

        except sqlite3.IntegrityError as e:
            logger.error(f"Ошибка регистрации пользователя: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[UserInfo]:
        """Аутентификация пользователя"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, username, email, password_hash, created_at
                FROM users WHERE username = ? AND password_hash = ?
            """,
                (username, password_hash),
            )

            row = cursor.fetchone()
            if row:
                # Получаем список ферм пользователя
                cursor.execute(
                    """
                    SELECT farm_id FROM user_farms WHERE user_id = ?
                """,
                    (row[0],),
                )
                farms = [r[0] for r in cursor.fetchall()]

                return UserInfo(
                    user_id=row[0],
                    username=row[1],
                    email=row[2],
                    password_hash=row[3],
                    farms=farms,
                    created_at=row[4],
                )

        return None

    def register_farm(self, farm_info: FarmInfo) -> bool:
        """Регистрация фермы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO farms (
                        farm_id, owner_id, farm_name, last_seen, local_ip,
                        public_ip, port, status, api_key, capabilities
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        farm_info.farm_id,
                        farm_info.owner_id,
                        farm_info.farm_name,
                        farm_info.last_seen,
                        farm_info.local_ip,
                        farm_info.public_ip,
                        farm_info.port,
                        farm_info.status,
                        farm_info.api_key,
                        json.dumps(farm_info.capabilities),
                    ),
                )

                # Добавляем владельца в user_farms если еще нет
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO user_farms (user_id, farm_id, access_level, granted_at)
                    VALUES (?, ?, 'owner', ?)
                """,
                    (farm_info.owner_id, farm_info.farm_id, time.time()),
                )

                conn.commit()

            logger.info(
                f"✅ Ферма {farm_info.farm_name} зарегистрирована: {farm_info.farm_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка регистрации фермы: {e}")
            return False

    def get_user_farms(self, user_id: str) -> list[FarmInfo]:
        """Получение списка ферм пользователя"""
        farms = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT f.farm_id, f.owner_id, f.farm_name, f.last_seen, f.local_ip,
                       f.public_ip, f.port, f.status, f.api_key, f.capabilities
                FROM farms f
                JOIN user_farms uf ON f.farm_id = uf.farm_id
                WHERE uf.user_id = ?
                ORDER BY f.last_seen DESC
            """,
                (user_id,),
            )

            for row in cursor.fetchall():
                farms.append(
                    FarmInfo(
                        farm_id=row[0],
                        owner_id=row[1],
                        farm_name=row[2],
                        last_seen=row[3],
                        local_ip=row[4],
                        public_ip=row[5],
                        port=row[6],
                        status=row[7],
                        api_key=row[8],
                        capabilities=json.loads(row[9]),
                    )
                )

        return farms

    def create_connection_request(
        self, user_id: str, farm_id: str, app_offer: dict
    ) -> Optional[str]:
        """Создание запроса на P2P соединение"""
        request_id = f"req_{secrets.token_hex(12)}"
        expires_at = time.time() + 300  # 5 минут на соединение

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO connection_requests (
                        request_id, user_id, farm_id, app_offer, created_at, status, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        request_id,
                        user_id,
                        farm_id,
                        json.dumps(app_offer),
                        time.time(),
                        "pending",
                        expires_at,
                    ),
                )
                conn.commit()

            logger.info(f"✅ Создан запрос на соединение: {request_id}")
            return request_id

        except Exception as e:
            logger.error(f"Ошибка создания запроса: {e}")
            return None


class TunnelBrokerServer:
    """Сервер-брокер для P2P туннелей"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.db = TunnelBrokerDB()
        self.app = Flask(__name__)
        CORS(self.app)
        self.setup_routes()

        # WebSocket сервер для realtime уведомлений
        self.ws_clients = {}  # farm_id -> websocket
        self.setup_websocket()

    def setup_routes(self):
        """Настройка HTTP маршрутов"""

        @self.app.route("/health")
        def health():
            return jsonify(
                {
                    "status": "healthy",
                    "service": "tunnel-broker",
                    "timestamp": time.time(),
                }
            )

        @self.app.route("/api/register", methods=["POST"])
        def register_user():
            data = request.json
            user_id = self.db.register_user(
                data.get("username"), data.get("email"), data.get("password")
            )

            if user_id:
                return jsonify(
                    {
                        "status": "success",
                        "user_id": user_id,
                        "message": "Пользователь зарегистрирован",
                    }
                )
            else:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Ошибка регистрации пользователя",
                        }
                    ),
                    400,
                )

        @self.app.route("/api/login", methods=["POST"])
        def login():
            data = request.json
            user = self.db.authenticate_user(data.get("username"), data.get("password"))

            if user:
                # Генерируем сессионный токен
                session_token = secrets.token_hex(32)

                return jsonify(
                    {
                        "status": "success",
                        "session_token": session_token,
                        "user_info": {
                            "user_id": user.user_id,
                            "username": user.username,
                            "farms_count": len(user.farms),
                        },
                    }
                )
            else:
                return (
                    jsonify({"status": "error", "message": "Неверные учетные данные"}),
                    401,
                )

        @self.app.route("/api/farm/register", methods=["POST"])
        def register_farm():
            data = request.json

            # Создаем ID фермы если не указан
            farm_id = data.get("farm_id") or f"farm_{secrets.token_hex(8)}"

            farm_info = FarmInfo(
                farm_id=farm_id,
                owner_id=data.get("owner_id"),
                farm_name=data.get("farm_name", f"Ферма {farm_id}"),
                last_seen=time.time(),
                local_ip=data.get("local_ip", ""),
                public_ip=request.remote_addr,
                port=data.get("port", 8000),
                api_key=data.get("api_key", secrets.token_hex(16)),
            )

            success = self.db.register_farm(farm_info)

            if success:
                return jsonify(
                    {
                        "status": "success",
                        "farm_id": farm_id,
                        "message": "Ферма зарегистрирована",
                    }
                )
            else:
                return (
                    jsonify({"status": "error", "message": "Ошибка регистрации фермы"}),
                    400,
                )

        @self.app.route("/api/farm/heartbeat", methods=["POST"])
        def farm_heartbeat():
            data = request.json
            farm_id = data.get("farm_id")

            if not farm_id:
                return jsonify({"status": "error", "message": "farm_id required"}), 400

            # Обновляем last_seen
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE farms SET last_seen = ?, public_ip = ?, status = 'online'
                    WHERE farm_id = ?
                """,
                    (time.time(), request.remote_addr, farm_id),
                )
                conn.commit()

            # Проверяем pending запросы
            pending_requests = self.get_pending_requests(farm_id)

            return jsonify(
                {
                    "status": "success",
                    "pending_requests": len(pending_requests),
                    "requests": pending_requests,
                }
            )

        @self.app.route("/api/farms/<user_id>")
        def get_user_farms(user_id):
            farms = self.db.get_user_farms(user_id)

            return jsonify(
                {"status": "success", "farms": [asdict(farm) for farm in farms]}
            )

        @self.app.route("/api/connect/request", methods=["POST"])
        def request_connection():
            data = request.json

            request_id = self.db.create_connection_request(
                user_id=data.get("user_id"),
                farm_id=data.get("farm_id"),
                app_offer=data.get("webrtc_offer", {}),
            )

            if request_id:
                # Уведомляем ферму через WebSocket
                self.notify_farm(
                    data.get("farm_id"),
                    {
                        "type": "connection_request",
                        "request_id": request_id,
                        "user_id": data.get("user_id"),
                    },
                )

                return jsonify(
                    {
                        "status": "success",
                        "request_id": request_id,
                        "message": "Запрос на соединение отправлен",
                    }
                )
            else:
                return (
                    jsonify({"status": "error", "message": "Ошибка создания запроса"}),
                    400,
                )

        @self.app.route("/api/connect/answer", methods=["POST"])
        def answer_connection():
            data = request.json
            request_id = data.get("request_id")
            farm_answer = data.get("webrtc_answer")

            # Обновляем запрос с ответом фермы
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE connection_requests
                    SET farm_answer = ?, status = 'answered'
                    WHERE request_id = ?
                """,
                    (json.dumps(farm_answer), request_id),
                )
                conn.commit()

            return jsonify({"status": "success", "message": "Ответ сохранен"})

        @self.app.route("/api/connect/status/<request_id>")
        def get_connection_status(request_id):
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT status, farm_answer FROM connection_requests
                    WHERE request_id = ?
                """,
                    (request_id,),
                )

                row = cursor.fetchone()
                if row:
                    farm_answer = json.loads(row[1]) if row[1] else None
                    return jsonify(
                        {
                            "status": "success",
                            "connection_status": row[0],
                            "farm_answer": farm_answer,
                        }
                    )
                else:
                    return (
                        jsonify({"status": "error", "message": "Запрос не найден"}),
                        404,
                    )

    def setup_websocket(self):
        """Настройка WebSocket сервера"""

        def new_client(client, server):
            logger.info(f"Новое WebSocket подключение: {client['address']}")

        def client_left(client, server):
            # Удаляем клиента из списка
            farm_id = None
            for fid, ws_client in self.ws_clients.items():
                if ws_client == client:
                    farm_id = fid
                    break

            if farm_id:
                del self.ws_clients[farm_id]
                logger.info(f"WebSocket отключен для фермы: {farm_id}")

        def message_received(client, server, message):
            try:
                data = json.loads(message)
                if data.get("type") == "register" and data.get("farm_id"):
                    self.ws_clients[data["farm_id"]] = client
                    logger.info(f"Ферма {data['farm_id']} зарегистрирована в WebSocket")
            except Exception as e:
                logger.error(f"Ошибка обработки WebSocket сообщения: {e}")

        # Запускаем WebSocket сервер в отдельном потоке
        def run_websocket():
            server = websocket_server.WebsocketServer(self.port + 1, host=self.host)
            server.set_fn_new_client(new_client)
            server.set_fn_client_left(client_left)
            server.set_fn_message_received(message_received)
            logger.info(f"WebSocket сервер запущен на {self.host}:{self.port + 1}")
            server.run_forever()

        ws_thread = threading.Thread(target=run_websocket, daemon=False)
        ws_thread.start()

    def notify_farm(self, farm_id: str, message: dict):
        """Отправка уведомления ферме через WebSocket"""
        if farm_id in self.ws_clients:
            try:
                client = self.ws_clients[farm_id]
                websocket_server.server.send_message(client, json.dumps(message))
                logger.info(f"Уведомление отправлено ферме {farm_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления ферме {farm_id}: {e}")

    def get_pending_requests(self, farm_id: str) -> list[dict]:
        """Получение ожидающих запросов для фермы"""
        requests = []

        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT request_id, user_id, app_offer, created_at
                FROM connection_requests
                WHERE farm_id = ? AND status = 'pending' AND expires_at > ?
            """,
                (farm_id, time.time()),
            )

            for row in cursor.fetchall():
                requests.append(
                    {
                        "request_id": row[0],
                        "user_id": row[1],
                        "app_offer": json.loads(row[2]),
                        "created_at": row[3],
                    }
                )

        return requests

    def cleanup_expired_requests(self):
        """Очистка просроченных запросов"""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM connection_requests WHERE expires_at < ?
            """,
                (time.time(),),
            )
            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Удалено {deleted} просроченных запросов")

    def start(self):
        """Запуск сервера"""
        logger.info(f"🚀 Tunnel Broker Server запущен на {self.host}:{self.port}")

        # Запускаем задачу очистки просроченных запросов
        def cleanup_task():
            while True:
                time.sleep(60)  # Каждую минуту
                self.cleanup_expired_requests()

        cleanup_thread = threading.Thread(target=cleanup_task, daemon=False)
        cleanup_thread.start()

        # Запускаем Flask приложение
        self.app.run(host=self.host, port=self.port, debug=False, threaded=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tunnel Broker Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")

    args = parser.parse_args()

    server = TunnelBrokerServer(host=args.host, port=args.port)
    server.start()
