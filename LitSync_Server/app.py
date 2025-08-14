# app.py
import asyncio
import logging
import sys
from typing import Any, Tuple

from quart import Quart, g
from quart_cors import cors
import socketio

import config
from core.change_detector import ChangeDetector
from core.clients import ClientRegistry
from core.context7 import Context7Client
from core.parser import LLMResponseParserV7
from core.prompt_builder import PromptBuilder
from core.request_coordinator import RequestCoordinator
from web.api import create_api_blueprint, create_context7_api_blueprint
from web.api_v2 import create_v2_blueprint
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


async def _teardown_context7_client(exception: Any = None) -> None:
    client = g.pop('context7_client', None)
    if client is not None:
        logger.debug("Закрытие экземпляра Context7Client из контекста запроса.")
        client.close()


def create_app() -> Tuple[Quart, socketio.AsyncServer, RequestCoordinator, ClientRegistry]:
    """
    Фабрика приложений: создает и конфигурирует экземпляры Quart и Socket.IO.
    Возвращает кортеж (app, sio, coordinator, registry)
    """
    logger.info("Инициализация приложения LitSync-Server (Quart)...")

    app = Quart(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # CORS: если ALLOWED_ORIGIN='*', отключаем credentials (требование quart-cors)
    allow_origin = config.ALLOWED_ORIGIN
    allow_credentials = allow_origin != "*"
    app = cors(
        app,
        allow_origin=allow_origin,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Настраиваем Socket.IO (ASGI)
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_interval=25,
        ping_timeout=10,
        logger=True,
        engineio_logger=True,
    )

    # --- Создание и внедрение зависимостей ---
    client_registry = ClientRegistry()
    llm_parser = LLMResponseParserV7()
    prompt_builder = PromptBuilder()
    change_detector = ChangeDetector(context_lines=3)
    coordinator = RequestCoordinator(
        sio=sio,
        registry=client_registry,
        public_base_url=config.PUBLIC_BASE_URL,
        upload_path_prefix=config.UPLOAD_PATH_PREFIX,
        default_timeout_seconds=config.DEFAULT_CLIENT_TIMEOUT_SECONDS,
    )

    # --- Регистрация Socket.IO пространства имен ---
    client_manager_ns = ClientManager(
        "/client",
        client_registry=client_registry,
        request_coordinator=coordinator,
    )
    sio.register_namespace(client_manager_ns)

    # --- Регистрация API блюпринтов ---
    api_blueprint = create_api_blueprint(
        registry=client_registry,
        parser=llm_parser,
        coordinator=coordinator,
        prompt_builder=prompt_builder,
        change_detector=change_detector,
    )
    context7_blueprint = create_context7_api_blueprint()
    v2_blueprint = create_v2_blueprint(registry=client_registry, coordinator=coordinator)

    app.register_blueprint(api_blueprint)
    app.register_blueprint(context7_blueprint)
    app.register_blueprint(v2_blueprint)

    @app.route("/")
    async def index() -> str:
        return "LitSync-Server is running (Quart)."

    app.teardown_appcontext(_teardown_context7_client)

    return app, sio, coordinator, client_registry


# Локальный запуск (для разработки)
if __name__ == "__main__":
    app_instance, sio_instance, _, _ = create_app()
    logger.info(f"Сервер LitSync-Server запускается на {config.HOST}:{config.PORT}")
    if config.TEST_SAVE_ENABLED:
        logger.warning(f"РЕЖИМ ОТЛАДКИ АКТИВЕН: Сырые запросы будут сохраняться в '{config.TEST_SAVE_PATH}'")

    import hypercorn.asyncio
    from hypercorn.config import Config as HyperConfig

    hyper_cfg = HyperConfig()
    hyper_cfg.bind = [f"{config.HOST}:{config.PORT}"]

    # Оборачиваем Quart приложение в ASGI приложение Socket.IO
    from socketio import ASGIApp
    asgi_app = ASGIApp(sio_instance, other_asgi_app=app_instance)

    asyncio.run(hypercorn.asyncio.serve(asgi_app, hyper_cfg))