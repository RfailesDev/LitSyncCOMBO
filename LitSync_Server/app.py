# app.py
import logging
import sys
from typing import Any

from flask import Flask, g
from flask_cors import CORS
from flask_socketio import SocketIO

import config
from core.change_detector import ChangeDetector
from core.clients import ClientRegistry
# ИМПОРТЫ ДЛЯ CONTEXT7
from core.context7 import Context7Client
from core.parser import LLMResponseParserV7
from core.prompt_builder import PromptBuilder
from core.request_coordinator import RequestCoordinator
from web.api import create_api_blueprint, create_context7_api_blueprint
from web.sockets import ClientManager

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def get_context7_client() -> Context7Client:
    """
    Возвращает экземпляр Context7Client для текущего контекста запроса.
    Создает новый экземпляр, если он еще не существует в `g`.
    """
    if 'context7_client' not in g:
        logger.debug("Создание нового экземпляра Context7Client для контекста запроса.")
        g.context7_client = Context7Client()
    return g.context7_client


def create_app() -> tuple[Flask, SocketIO]:
    """
    Фабрика приложений: создает и конфигурирует экземпляры Flask и SocketIO.
    """
    logger.info("Инициализация приложения LitSync-Server...")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Настраиваем встроенный heartbeat с разумными таймаутами.
    sio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        ping_interval=25,
        ping_timeout=10,
        logger=True,
        engineio_logger=True
    )

    # --- Создание и внедрение зависимостей ---
    client_registry = ClientRegistry()
    llm_parser = LLMResponseParserV7()
    request_coordinator = RequestCoordinator(sio)
    prompt_builder = PromptBuilder()
    change_detector = ChangeDetector(context_lines=3)

    # --- Регистрация компонентов приложения ---
    client_manager_ns = ClientManager(
        "/client",
        client_registry=client_registry,
        request_coordinator=request_coordinator,
    )
    sio.on_namespace(client_manager_ns)

    api_blueprint = create_api_blueprint(
        registry=client_registry,
        parser=llm_parser,
        sio=sio,
        coordinator=request_coordinator,
        prompt_builder=prompt_builder,
        change_detector=change_detector,
    )
    context7_blueprint = create_context7_api_blueprint()

    app.register_blueprint(api_blueprint)
    app.register_blueprint(context7_blueprint)

    @app.route("/")
    def index() -> str:
        return "LitSync-Server is running."

    @app.teardown_appcontext
    def teardown_context7_client(exception: Any = None) -> None:
        """Закрывает клиент Context7, если он был создан в этом контексте запроса."""
        client = g.pop('context7_client', None)
        if client is not None:
            logger.debug("Закрытие экземпляра Context7Client из контекста запроса.")
            client.close()

    return app, sio


# --- Запуск сервера ---
if __name__ == "__main__":
    app_instance, sio_instance = create_app()
    logger.info(f"Сервер LitSync-Server запускается на {config.HOST}:{config.PORT}")
    if config.TEST_SAVE_ENABLED:
        logger.warning(f"РЕЖИМ ОТЛАДКИ АКТИВЕН: Сырые запросы будут сохраняться в '{config.TEST_SAVE_PATH}'")

    sio_instance.run(app_instance, host=config.HOST, port=config.PORT, use_reloader=True)