import logging
from typing import Any, Dict

import socketio

from core.clients import ClientRegistry
from core.request_coordinator import RequestCoordinator

logger = logging.getLogger(__name__)


class ClientManager(socketio.AsyncNamespace):
    """
    Пространство имен для инкапсуляции всей логики, связанной с клиентами.
    Возвращена зависимость от RequestCoordinator. ASGI/async вариант.
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

    async def on_connect(self, sid: str, environ: Dict[str, Any]) -> None:
        """Вызывается при подключении нового клиента."""
        ip = environ.get("REMOTE_ADDR") or "unknown"
        self.registry.add(sid=sid, ip=ip)

    async def on_disconnect(self, sid: str) -> None:
        """Вызывается при штатном или принудительном отключении клиента."""
        self.registry.remove(sid=sid)

    async def on_register(self, sid: str, data: Dict[str, str]) -> None:
        """Событие для регистрации клиента. Обрабатывает "захват сессии"."""
        old_sid_to_disconnect = self.registry.register(sid=sid, data=data)
        if old_sid_to_disconnect:
            logger.warning(
                f"Принудительно отключаю старого клиента {old_sid_to_disconnect} из-за регистрации нового клиента с тем же именем."
            )
            await self.disconnect(old_sid_to_disconnect, namespace=self.namespace)

    async def on_file_tree_response(self, sid: str, data: Dict[str, Any]) -> None:
        """
        Получает ответ от клиента с деревом файлов и передает его координатору.
        """
        logger.debug(f"Получен file_tree_response от {sid}")
        await self.request_coordinator.handle_response(sid, data)

    async def on_file_content_response(self, sid: str, data: Dict[str, Any]) -> None:
        """
        Получает ответ от клиента с содержимым файлов и передает его координатору.
        """
        logger.debug(f"Получен file_content_response от {sid}")
        await self.request_coordinator.handle_response(sid, data)