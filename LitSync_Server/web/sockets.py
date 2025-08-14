import logging
from typing import Any, Dict

from flask import request
from flask_socketio import Namespace

from core.clients import ClientRegistry
from core.request_coordinator import RequestCoordinator

logger = logging.getLogger(__name__)


class ClientManager(Namespace):
    """
    Пространство имен для инкапсуляции всей логики, связанной с клиентами.
    Возвращена зависимость от RequestCoordinator.
    """
    def __init__(
        self,
        namespace: str,
        client_registry: ClientRegistry,
        request_coordinator: RequestCoordinator,
    ):
        super().__init__(namespace)
        self.registry = client_registry
        self.request_coordinator = request_coordinator

    def on_connect(self, *args: Any) -> None:
        """Вызывается при подключении нового клиента."""
        self.registry.add(sid=request.sid, ip=request.remote_addr)

    def on_disconnect(self, *args: Any) -> None:
        """Вызывается при штатном или принудительном отключении клиента."""
        self.registry.remove(sid=request.sid)

    def on_register(self, data: Dict[str, str]) -> None:
        """Событие для регистрации клиента. Обрабатывает "захват сессии"."""
        old_sid_to_disconnect = self.registry.register(sid=request.sid, data=data)
        if old_sid_to_disconnect:
            logger.warning(
                f"Принудительно отключаю старого клиента {old_sid_to_disconnect} "
                f"из-за регистрации нового клиента с тем же именем."
            )
            self.socketio.disconnect(
                old_sid_to_disconnect,
                namespace=self.namespace,
                ignore_queue=True
            )

    def on_file_tree_response(self, data: Dict[str, Any]) -> None:
        """
        Получает ответ от клиента с деревом файлов и передает его координатору.
        """
        logger.debug(f"Получен file_tree_response от {request.sid}")
        self.request_coordinator.handle_response(request.sid, data)

    def on_file_content_response(self, data: Dict[str, Any]) -> None:
        """
        Получает ответ от клиента с содержимым файлов и передает его координатору.
        """
        logger.debug(f"Получен file_content_response от {request.sid}")
        self.request_coordinator.handle_response(request.sid, data)