#!/usr/bin/env python3
"""
Mobile App - веб-приложение для мобильных устройств
Подключается к фермам через P2P туннели
"""

import asyncio
import logging
import os
import secrets
import time

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WebRTCManager:
    """Менеджер WebRTC соединений для мобильного приложения"""

    def __init__(self):
        self.active_connections = {}  # farm_id -> connection_info

    async def create_offer(self) -> dict:
        """Создание WebRTC offer для соединения с фермой"""
        # В реальной реализации здесь будет создание WebRTC offer
        # Для демонстрации возвращаем заглушку
        offer = {
            "type": "offer",
            "sdp": f"v=0\r\no=- {int(time.time())} 0 IN IP4 127.0.0.1\r\ns=-\r\n...",
        }

        logger.info("WebRTC offer создан")
        return offer

    async def handle_answer(self, farm_id: str, answer: dict):
        """Обработка WebRTC answer от фермы"""
        logger.info(f"WebRTC answer получен от фермы {farm_id}")

        # В реальности здесь обработка answer и установка соединения
        self.active_connections[farm_id] = {
            "status": "connected",
            "connected_at": time.time(),
        }

        return True

    def send_api_request(
        self, farm_id: str, endpoint: str, method: str = "GET", data: dict = None
    ) -> dict:
        """Отправка API запроса через WebRTC туннель"""
        if farm_id not in self.active_connections:
            return {"error": "Нет соединения с фермой"}

        request_id = secrets.token_hex(8)

        # В реальности отправляем через WebRTC DataChannel
        request_data = {
            "type": "api_request",
            "request_id": request_id,
            "endpoint": endpoint,
            "method": method,
            "data": data,
        }

        logger.info(f"API запрос отправлен в ферму {farm_id}: {method} {endpoint}")

        # Заглушка ответа (в реальности ждем ответ через WebRTC)
        return {
            "status": "success",
            "data": {
                "temp_inside": 25.8,
                "humidity": 55.2,
                "co2": 450,
                "timestamp": time.time(),
            },
        }


class TunnelMobileApp:
    """Мобильное приложение для подключения к фермам"""

    def __init__(self, broker_url: str):
        self.broker_url = broker_url.rstrip("/")
        self.app = Flask(__name__)
        self.app.secret_key = secrets.token_hex(32)
        CORS(self.app)

        self.webrtc = WebRTCManager()
        self.setup_routes()

    def setup_routes(self):
        """Настройка маршрутов Flask"""

        @self.app.route("/")
        def index():
            if "user_id" not in session:
                return redirect(url_for("login"))
            return render_template("mobile_index.html")

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            if request.method == "GET":
                return render_template("mobile_login.html")

            username = request.form.get("username")
            password = request.form.get("password")

            # Аутентификация через Tunnel Broker
            try:
                response = requests.post(
                    f"{self.broker_url}/api/login",
                    json={"username": username, "password": password},
                    timeout=10,
                )

                if response.status_code == 200:
                    result = response.json()
                    session["user_id"] = result["user_info"]["user_id"]
                    session["username"] = result["user_info"]["username"]
                    session["session_token"] = result["session_token"]

                    return redirect(url_for("index"))
                else:
                    return render_template(
                        "mobile_login.html", error="Неверные учетные данные"
                    )

            except Exception as e:
                logger.error(f"Ошибка авторизации: {e}")
                return render_template(
                    "mobile_login.html", error="Ошибка подключения к серверу"
                )

        @self.app.route("/register", methods=["GET", "POST"])
        def register():
            if request.method == "GET":
                return render_template("mobile_register.html")

            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")

            try:
                response = requests.post(
                    f"{self.broker_url}/api/register",
                    json={"username": username, "email": email, "password": password},
                    timeout=10,
                )

                if response.status_code == 200:
                    return render_template(
                        "mobile_login.html",
                        success="Регистрация успешна, войдите в систему",
                    )
                else:
                    result = response.json()
                    return render_template(
                        "mobile_register.html",
                        error=result.get("message", "Ошибка регистрации"),
                    )

            except Exception as e:
                logger.error(f"Ошибка регистрации: {e}")
                return render_template(
                    "mobile_register.html", error="Ошибка подключения к серверу"
                )

        @self.app.route("/logout")
        def logout():
            session.clear()
            return redirect(url_for("login"))

        @self.app.route("/api/farms")
        def get_farms():
            if "user_id" not in session:
                return jsonify({"error": "Не авторизован"}), 401

            try:
                response = requests.get(
                    f"{self.broker_url}/api/farms/{session['user_id']}", timeout=10
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return jsonify({"error": "Ошибка получения списка ферм"}), 500

            except Exception as e:
                logger.error(f"Ошибка получения ферм: {e}")
                return jsonify({"error": "Ошибка подключения"}), 500

        @self.app.route("/api/connect/<farm_id>", methods=["POST"])
        async def connect_to_farm(farm_id):
            if "user_id" not in session:
                return jsonify({"error": "Не авторизован"}), 401

            try:
                # Создаем WebRTC offer
                webrtc_offer = await self.webrtc.create_offer()

                # Отправляем запрос на соединение в Tunnel Broker
                response = requests.post(
                    f"{self.broker_url}/api/connect/request",
                    json={
                        "user_id": session["user_id"],
                        "farm_id": farm_id,
                        "webrtc_offer": webrtc_offer,
                    },
                    timeout=10,
                )

                if response.status_code == 200:
                    result = response.json()
                    request_id = result["request_id"]

                    # Ждем ответ от фермы (в реальности через WebSocket или polling)
                    connection_established = await self.wait_for_connection(
                        request_id, farm_id
                    )

                    if connection_established:
                        return jsonify(
                            {
                                "status": "success",
                                "message": "Соединение с фермой установлено",
                                "farm_id": farm_id,
                            }
                        )
                    else:
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "message": "Не удалось установить соединение с фермой",
                                }
                            ),
                            408,
                        )
                else:
                    return jsonify({"error": "Ошибка запроса соединения"}), 500

            except Exception as e:
                logger.error(f"Ошибка подключения к ферме {farm_id}: {e}")
                return jsonify({"error": "Ошибка подключения"}), 500

        @self.app.route("/api/farm/<farm_id>/data")
        def get_farm_data(farm_id):
            if "user_id" not in session:
                return jsonify({"error": "Не авторизован"}), 401

            # Получаем данные через WebRTC туннель
            data = self.webrtc.send_api_request(farm_id, "/api/data/current")

            return jsonify(data)

        @self.app.route("/api/farm/<farm_id>/history")
        def get_farm_history(farm_id):
            if "user_id" not in session:
                return jsonify({"error": "Не авторизован"}), 401

            hours = request.args.get("hours", 6, type=int)
            data = self.webrtc.send_api_request(
                farm_id, f"/api/data/history?hours={hours}"
            )

            return jsonify(data)

    async def wait_for_connection(
        self, request_id: str, farm_id: str, timeout: int = 30
    ) -> bool:
        """Ожидание установки P2P соединения"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.broker_url}/api/connect/status/{request_id}", timeout=5
                )

                if response.status_code == 200:
                    result = response.json()
                    status = result.get("connection_status")

                    if status == "answered":
                        # Получаем WebRTC answer от фермы
                        farm_answer = result.get("farm_answer")
                        if farm_answer:
                            # Обрабатываем answer и устанавливаем соединение
                            success = await self.webrtc.handle_answer(
                                farm_id, farm_answer
                            )
                            return success

                # Ждем 2 секунды перед следующей проверкой
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Ошибка проверки статуса соединения: {e}")
                await asyncio.sleep(2)

        return False

    def run(self, host: str = "0.0.0.0", port: int = 5000):
        """Запуск приложения"""
        logger.info(f"🚀 Mobile App запущено на {host}:{port}")
        self.app.run(host=host, port=port, debug=True)


# HTML шаблоны
TEMPLATES = {
    "mobile_login.html": """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>КУБ-1063 Mobile - Вход</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px); }
    </style>
</head>
<body>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-md-6 col-lg-4">
                <div class="card shadow-lg">
                    <div class="card-body p-4">
                        <div class="text-center mb-4">
                            <h3 class="card-title">🏭 КУБ-1063</h3>
                            <p class="text-muted">Мобильное приложение</p>
                        </div>

                        {% if error %}
                        <div class="alert alert-danger">{{ error }}</div>
                        {% endif %}

                        {% if success %}
                        <div class="alert alert-success">{{ success }}</div>
                        {% endif %}

                        <form method="POST">
                            <div class="mb-3">
                                <label for="username" class="form-label">Логин</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>

                            <div class="mb-3">
                                <label for="password" class="form-label">Пароль</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>

                            <button type="submit" class="btn btn-primary w-100 mb-3">Войти</button>
                        </form>

                        <div class="text-center">
                            <a href="/register" class="text-decoration-none">Нет аккаунта? Зарегистрироваться</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
""",
    "mobile_register.html": """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>КУБ-1063 Mobile - Регистрация</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px); }
    </style>
</head>
<body>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-md-6 col-lg-4">
                <div class="card shadow-lg">
                    <div class="card-body p-4">
                        <div class="text-center mb-4">
                            <h3 class="card-title">📝 Регистрация</h3>
                            <p class="text-muted">Создать новый аккаунт</p>
                        </div>

                        {% if error %}
                        <div class="alert alert-danger">{{ error }}</div>
                        {% endif %}

                        <form method="POST">
                            <div class="mb-3">
                                <label for="username" class="form-label">Логин</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>

                            <div class="mb-3">
                                <label for="email" class="form-label">Email</label>
                                <input type="email" class="form-control" id="email" name="email" required>
                            </div>

                            <div class="mb-3">
                                <label for="password" class="form-label">Пароль</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>

                            <button type="submit" class="btn btn-primary w-100 mb-3">Зарегистрироваться</button>
                        </form>

                        <div class="text-center">
                            <a href="/login" class="text-decoration-none">Уже есть аккаунт? Войти</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
""",
    "mobile_index.html": """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>КУБ-1063 Mobile - Мои фермы</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px); margin-bottom: 1rem; }
        .farm-card { cursor: pointer; transition: transform 0.2s; }
        .farm-card:hover { transform: translateY(-2px); }
        .status-online { color: #28a745; }
        .status-offline { color: #dc3545; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container">
            <span class="navbar-brand">🏭 КУБ-1063 Mobile</span>
            <a href="/logout" class="btn btn-outline-light btn-sm">Выйти</a>
        </div>
    </nav>

    <div class="container py-4">
        <div id="farmsContainer">
            <div class="text-center py-5">
                <div class="spinner-border" role="status"></div>
                <p class="mt-2">Загрузка ферм...</p>
            </div>
        </div>

        <!-- Модальное окно с данными фермы -->
        <div class="modal fade" id="farmModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="farmModalTitle">Данные фермы</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" id="farmModalBody">
                        <!-- Данные фермы будут загружены здесь -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let farms = [];
        let currentFarmId = null;

        // Загрузка списка ферм
        async function loadFarms() {
            try {
                const response = await fetch('/api/farms');
                const data = await response.json();

                if (data.status === 'success') {
                    farms = data.farms;
                    displayFarms();
                } else {
                    document.getElementById('farmsContainer').innerHTML =
                        '<div class="alert alert-danger">Ошибка загрузки ферм</div>';
                }
            } catch (error) {
                console.error('Ошибка:', error);
                document.getElementById('farmsContainer').innerHTML =
                    '<div class="alert alert-danger">Ошибка подключения</div>';
            }
        }

        // Отображение списка ферм
        function displayFarms() {
            const container = document.getElementById('farmsContainer');

            if (farms.length === 0) {
                container.innerHTML = '<div class="alert alert-info">У вас пока нет ферм</div>';
                return;
            }

            let html = '<div class="row">';

            farms.forEach(farm => {
                const isOnline = Date.now() / 1000 - farm.last_seen < 600; // 10 минут
                const statusClass = isOnline ? 'status-online' : 'status-offline';
                const statusText = isOnline ? 'Онлайн' : 'Офлайн';

                html += `
                    <div class="col-md-6 col-lg-4 mb-3">
                        <div class="card farm-card" onclick="connectToFarm('${farm.farm_id}')">
                            <div class="card-body">
                                <h5 class="card-title">${farm.farm_name}</h5>
                                <p class="card-text text-muted">ID: ${farm.farm_id}</p>
                                <div class="d-flex justify-content-between align-items-center">
                                    <small class="${statusClass}">● ${statusText}</small>
                                    <small class="text-muted">${new Date(farm.last_seen * 1000).toLocaleString('ru-RU')}</small>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            container.innerHTML = html;
        }

        // Подключение к ферме
        async function connectToFarm(farmId) {
            const farm = farms.find(f => f.farm_id === farmId);
            if (!farm) return;

            currentFarmId = farmId;

            // Показываем модальное окно с индикатором загрузки
            document.getElementById('farmModalTitle').textContent = farm.farm_name;
            document.getElementById('farmModalBody').innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border" role="status"></div>
                    <p class="mt-2">Подключение к ферме...</p>
                </div>
            `;

            const modal = new bootstrap.Modal(document.getElementById('farmModal'));
            modal.show();

            try {
                // Устанавливаем P2P соединение
                const connectResponse = await fetch(`/api/connect/${farmId}`, {
                    method: 'POST'
                });

                const connectResult = await connectResponse.json();

                if (connectResult.status === 'success') {
                    // Соединение установлено, загружаем данные
                    await loadFarmData(farmId);
                } else {
                    document.getElementById('farmModalBody').innerHTML = `
                        <div class="alert alert-danger">
                            ${connectResult.message || 'Ошибка подключения к ферме'}
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Ошибка подключения:', error);
                document.getElementById('farmModalBody').innerHTML = `
                    <div class="alert alert-danger">Ошибка подключения к ферме</div>
                `;
            }
        }

        // Загрузка данных фермы
        async function loadFarmData(farmId) {
            try {
                const response = await fetch(`/api/farm/${farmId}/data`);
                const data = await response.json();

                if (data.status === 'success') {
                    displayFarmData(data.data);
                } else {
                    document.getElementById('farmModalBody').innerHTML = `
                        <div class="alert alert-warning">Нет данных от фермы</div>
                    `;
                }
            } catch (error) {
                console.error('Ошибка загрузки данных:', error);
                document.getElementById('farmModalBody').innerHTML = `
                    <div class="alert alert-danger">Ошибка получения данных</div>
                `;
            }
        }

        // Отображение данных фермы
        function displayFarmData(data) {
            const html = `
                <div class="row">
                    <div class="col-6 text-center">
                        <div class="card bg-light">
                            <div class="card-body">
                                <h3 class="text-primary">${data.temp_inside}°C</h3>
                                <small class="text-muted">Температура</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-6 text-center">
                        <div class="card bg-light">
                            <div class="card-body">
                                <h3 class="text-info">${data.humidity}%</h3>
                                <small class="text-muted">Влажность</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-6 text-center mt-2">
                        <div class="card bg-light">
                            <div class="card-body">
                                <h3 class="text-warning">${data.co2}</h3>
                                <small class="text-muted">CO₂ (ppm)</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-6 text-center mt-2">
                        <div class="card bg-light">
                            <div class="card-body">
                                <h3 class="text-success">Онлайн</h3>
                                <small class="text-muted">Статус</small>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="mt-3">
                    <small class="text-muted">
                        Последнее обновление: ${new Date(data.timestamp * 1000).toLocaleString('ru-RU')}
                    </small>
                </div>
            `;

            document.getElementById('farmModalBody').innerHTML = html;
        }

        // Загружаем фермы при загрузке страницы
        document.addEventListener('DOMContentLoaded', loadFarms);
    </script>
</body>
</html>
""",
}


def create_templates():
    """Создание HTML шаблонов"""
    templates_dir = "tunnel_system/templates"
    os.makedirs(templates_dir, exist_ok=True)

    for filename, content in TEMPLATES.items():
        with open(f"{templates_dir}/{filename}", "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mobile App for Farm Tunnels")
    parser.add_argument("--broker", required=True, help="URL Tunnel Broker сервера")
    parser.add_argument("--host", default="0.0.0.0", help="Host для приложения")
    parser.add_argument("--port", type=int, default=5000, help="Port для приложения")

    args = parser.parse_args()

    # Создаем шаблоны
    create_templates()

    # Создаем и запускаем приложение
    app = TunnelMobileApp(args.broker)
    app.run(host=args.host, port=args.port)
