# core/request_coordinator.py
"""
Координатор асинхронных запросов к Python-клиентам.
Поддерживает 2 механизма:
- Socket.IO: сервер инициирует события, клиент отвечает через socketio события.
- Polling API: клиент периодически опрашивает сервер и получает задания, затем отправляет результаты на API upload-ссылки.
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

import socketio

from core.clients import ClientRegistry

logger = logging.getLogger(__name__)


class RequestCoordinator:
	"""
	Управляет жизненным циклом запросов от API к Python-клиентам.
	Асинхронная версия с asyncio.Future для ожидания ответов.
	"""

	def __init__(
		self,
		*,
		sio: socketio.AsyncServer,
		registry: ClientRegistry,
		public_base_url: str,
		upload_path_prefix: str,
		default_timeout_seconds: int = 60,
	):
		self._sio = sio
		self._registry = registry
		self._default_timeout_seconds = default_timeout_seconds
		self._pending_requests: Dict[str, asyncio.Future] = {}
		self._pending_lock = asyncio.Lock()
		self._public_base_url = public_base_url.rstrip("/")
		self._upload_prefix = upload_path_prefix.rstrip("/")

		# Очередь команд для polling-режима: client_sid -> список команд
		self._polling_commands: Dict[str, list[dict]] = {}
		self._polling_lock = asyncio.Lock()

	def _make_request_payload(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
		payload = data.copy() if data else {}
		payload.setdefault("request_id", str(uuid.uuid4()))
		return payload

	async def make_request(self, sid: str, event_name: str, data: Optional[Dict[str, Any]] = None) -> Any:
		"""
		Отправляет запрос клиенту и асинхронно ждет ответа по request_id.
		Используется для коротких ответов (метаданные/дерево/содержимое), возвращаемых по сокету или через polling upload.
		"""
		request_payload = self._make_request_payload(data)
		request_id = request_payload["request_id"]

		fut: asyncio.Future = asyncio.get_event_loop().create_future()
		async with self._pending_lock:
			self._pending_requests[request_id] = fut

		meta = self._registry.get_client_metadata(sid) or {}
		transport = meta.get("transport", "socket")
		logger.info(f"Отправка запроса '{event_name}' клиенту {sid} (req_id: {request_id}, transport={transport})")

		if transport == "polling":
			# Формируем polling-команду с upload_url для ответа
			command = {
				"type": event_name,
				"request_id": request_id,
				"payload": data or {},
				"upload_url": self.build_upload_url(sid, request_id),
			}
			await self.enqueue_polling_command(sid, command)
		else:
			# Для socket-клиентов также передаем upload_url, чтобы большие ответы пришли через HTTP API
			request_payload["upload_url"] = self.build_upload_url(sid, request_id)
			await self._sio.emit(event_name, request_payload, namespace="/client", to=sid)

		try:
			return await asyncio.wait_for(fut, timeout=self._default_timeout_seconds)
		except asyncio.TimeoutError:
			logger.error(
				f"Таймаут ({self._default_timeout_seconds}s) ожидания ответа от клиента {sid} для req_id: {request_id}"
			)
			raise TimeoutError()
		finally:
			async with self._pending_lock:
				self._pending_requests.pop(request_id, None)

	async def handle_response(self, sid: str, data: Dict[str, Any]) -> None:
		"""
		Обрабатывает входящий ответ от клиента и "пробуждает" ожидающий Future.
		"""
		request_id = data.get("request_id")
		if not request_id:
			logger.warning(f"Получен ответ от {sid} без request_id. Игнорируется.")
			return

		async with self._pending_lock:
			fut = self._pending_requests.get(request_id)

		if fut and not fut.done():
			payload = data.get("payload", {})
			fut.set_result(payload)
		else:
			logger.warning(
				f"Получен ответ для неизвестного или просроченного req_id: {request_id}"
			)

	async def emit_update_files_command(self, sid: str, files_to_update: list[dict]) -> None:
		"""
		Отправляет команду на обновление файлов.
		Для polling-клиентов публикуется команда в очередь /v2/check.
		"""
		meta = self._registry.get_client_metadata(sid) or {}
		transport = meta.get("transport", "socket")
		if transport == "polling":
			command = {
				"type": "update_files",
				"request_id": str(uuid.uuid4()),
				"payload": {"files": files_to_update},
				"upload_url": None,
			}
			await self.enqueue_polling_command(sid, command)
			logger.info(f"Команда update_files поставлена в очередь polling для {sid} ({len(files_to_update)} файлов)")
			return
		await self._sio.emit(
			"update_files",
			{"files": files_to_update},
			namespace="/client",
			to=sid,
		)

	# ---------- Механизм для Polling клиентов ----------
	async def enqueue_polling_command(self, sid: str, command: dict) -> None:
		async with self._polling_lock:
			self._polling_commands.setdefault(sid, []).append(command)

	async def fetch_polling_commands(self, sid: str) -> list[dict]:
		async with self._polling_lock:
			cmds = self._polling_commands.get(sid) or []
			self._polling_commands[sid] = []
			return cmds

	def build_upload_url(self, sid: str, request_id: Optional[str] = None) -> str:
		"""Генерирует публичную upload-ссылку для клиента (используется в командах)."""
		req = request_id or str(uuid.uuid4())
		return f"{self._public_base_url}{self._upload_prefix}/{sid}/{req}"