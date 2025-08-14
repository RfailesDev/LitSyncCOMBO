# core/clients.py
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ClientRegistry:
	"""
	Потокобезопасный класс для управления состоянием подключенных клиентов.
	Сохраняет метаданные (hostname, root_dir_name) при регистрации.
	"""

	def __init__(self) -> None:
		self._clients: Dict[str, Dict[str, Any]] = {}
		self._hostname_to_sid: Dict[str, str] = {}
		self._lock = threading.Lock()

	def add(self, sid: str, ip: str) -> None:
		"""Добавляет нового клиента в пул при подключении."""
		with self._lock:
			logger.info(f"Клиент подключается: sid={sid}, ip={ip}")
			self._clients[sid] = {
				"sid": sid,
				"ip": ip,
				"hostname": "Pending registration...",
				"root_dir_name": None,
				"transport": "socket" if ip != "polling" else "polling",
			}
			logger.info(f"Клиент {sid} добавлен в пул. Ожидание регистрации.")

	def remove(self, sid: str) -> None:
		"""Удаляет клиента из пула и всех связанных индексов."""
		with self._lock:
			if sid in self._clients:
				client_info = self._clients.pop(sid)
				hostname = client_info.get("hostname")
				if hostname and hostname != "Pending registration...":
					# Удаляем из индекса, только если SID совпадает,
					# чтобы не удалить нового клиента при отключении старого
					if self._hostname_to_sid.get(hostname) == sid:
						del self._hostname_to_sid[hostname]

				logger.info(
					f"Клиент '{hostname}' (sid={sid}) отключен. Пул и индексы очищены."
				)
			else:
				logger.warning(f"Попытка удаления уже удаленного клиента: sid={sid}")

	def register(self, sid: str, data: Dict[str, str]) -> Optional[str]:
		"""
		Регистрирует клиента, добавляя метаданные (hostname, root_dir_name).
		Если клиент с таким hostname уже существует, возвращает SID старого клиента
		для принудительного отключения.

		Возвращает: SID старого клиента или None.
		"""
		with self._lock:
			if sid not in self._clients:
				logger.warning(f"Попытка регистрации от неизвестного SID ({sid}). Игнорируется.")
				return None

			hostname = data.get("id")
			root_dir_name = data.get("root_dir_name", "project")

			if not hostname:
				logger.warning(f"Попытка регистрации для SID {sid} без 'id'. Игнорируется.")
				return None

			old_sid_to_disconnect: Optional[str] = None

			if hostname in self._hostname_to_sid:
				old_sid = self._hostname_to_sid[hostname]
				if old_sid != sid:
					logger.warning(
						f"Обнаружен конфликт имен! Имя '{hostname}' уже используется клиентом {old_sid}. "
						f"Новый клиент {sid} 'захватывает' сессию."
					)
					old_sid_to_disconnect = old_sid
					if old_sid in self._clients:
						self._clients[old_sid]['hostname'] = f"EVICTED by {sid}"

			self._clients[sid]["hostname"] = hostname
			self._clients[sid]["root_dir_name"] = root_dir_name
			self._hostname_to_sid[hostname] = sid

			logger.info(f"Клиент {sid} успешно зарегистрирован как '{hostname}' с корневой папкой '{root_dir_name}'")

			return old_sid_to_disconnect

	def is_present(self, sid: str) -> bool:
		"""Проверяет, подключен ли клиент с данным SID."""
		with self._lock:
			return sid in self._clients

	def get_hostname(self, sid: str) -> str:
		"""Возвращает hostname клиента или 'N/A'."""
		with self._lock:
			return self._clients.get(sid, {}).get("hostname", "N/A")

	def get_all_registered(self) -> List[Dict[str, str]]:
		"""Возвращает список всех зарегистрированных и активных клиентов для API."""
		with self._lock:
			return [
				{"id": info["sid"], "name": info.get("hostname", "Unnamed")}
				for sid, info in self._clients.items()
				if info.get("hostname") and not info.get("hostname", "").startswith("EVICTED")
			]

	def get_client_metadata(self, sid: str) -> Optional[Dict[str, Any]]:
		"""Возвращает полный словарь метаданных для клиента по его SID."""
		with self._lock:
			client_data = self._clients.get(sid)
			return client_data.copy() if client_data else None

	def get_all_clients_info(self) -> List[Dict[str, Any]]:
		"""
		Возвращает список словарей с полной информацией о каждом клиенте.
		Нужно для HeartbeatManager, чтобы фильтровать вытесненных клиентов.
		"""
		with self._lock:
			return list(self._clients.values())