# core/request_coordinator.py
"""
Координатор асинхронных запросов к Python-клиентам.
Этот модуль необходим для синхронного API и теперь будет работать
корректно в среде с несколькими воркерами.
"""
import logging
import threading
import uuid
from typing import Any, Dict, Optional

from eventlet.event import Event
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

# Таймаут увеличен до 60 секунд.
# Это защищает от медленных дисковых операций на клиенте.
DEFAULT_CLIENT_TIMEOUT_SECONDS = 60


class RequestCoordinator:
    """
    Управляет жизненным циклом запросов от API к Python-клиентам.
    """

    def __init__(self, sio: SocketIO):
        self._sio = sio
        self._pending_requests: Dict[str, Event] = {}
        self._lock = threading.Lock()

    def make_request(
        self, sid: str, event_name: str, data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Отправляет запрос клиенту и блокирующе ждет ответа.
        """
        request_id = str(uuid.uuid4())
        event = Event()

        with self._lock:
            self._pending_requests[request_id] = event

        request_payload = data or {}
        request_payload["request_id"] = request_id

        logger.info(f"Отправка запроса '{event_name}' клиенту {sid} (req_id: {request_id})")
        self._sio.emit(event_name, request_payload, namespace="/client", to=sid)

        try:
            response_payload = event.wait(timeout=DEFAULT_CLIENT_TIMEOUT_SECONDS)
            logger.info(f"Получен ответ для req_id: {request_id}")
            return response_payload
        except TimeoutError:
            logger.error(
                f"Таймаут ({DEFAULT_CLIENT_TIMEOUT_SECONDS}s) ожидания ответа от клиента {sid} для req_id: {request_id}"
            )
            raise
        finally:
            with self._lock:
                self._pending_requests.pop(request_id, None)

    def handle_response(self, sid: str, data: Dict[str, Any]) -> None:
        """
        Обрабатывает входящий ответ от клиента и "пробуждает" ожидающий greenlet.
        """
        request_id = data.get("request_id")
        if not request_id:
            logger.warning(f"Получен ответ от {sid} без request_id. Игнорируется.")
            return

        with self._lock:
            event = self._pending_requests.get(request_id)

        if event:
            payload = data.get("payload", {})
            event.send(payload)
        else:
            logger.warning(
                f"Получен ответ для неизвестного или просроченного req_id: {request_id}"
            )