# worker.py
"""
Сетевой воркер для LitSync-Client.
Финальная, стабильная версия.
- Логика подключения полагается на встроенные механизмы библиотеки.
- Обработчики событий соответствуют RPC-протоколу сервера.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chardet
import requests
import socketio
from PyQt6.QtCore import QObject, pyqtSignal

from config import (BINARY_DETECTION_CHUNK_SIZE, BINARY_FILE_EXTENSIONS,
                    CLIENT_NAMESPACE, CONNECTION_TIMEOUT_SECONDS,
                    EXCLUDED_DIRS, MAX_FILE_SIZE_BYTES,
                    RECONNECT_DELAY_MAX_SECONDS, RECONNECT_DELAY_SECONDS,
                    ROOT_DIR, HTTP_URL_VIA_PROXY, HTTPS_URL_DIRECT,
                    SOCKS_PROXY_URL, PROXY_TEST_URL, PROXY_TEST_TIMEOUT_SECONDS)
from pathfilter import GitignoreFilter


class SecurityException(Exception):
    """Исключение для ошибок безопасности, например, попытки доступа к файлам вне проекта."""
    pass


def _is_file_unsuitable_for_sync(path: Path) -> Optional[str]:
    """
    Выполняет быструю многоуровневую проверку, чтобы определить, следует ли пропустить файл.
    """
    if path.suffix.lower() in BINARY_FILE_EXTENSIONS:
        return f"File extension '{path.suffix}' is in the binary blacklist."
    try:
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return f"File size {file_size} bytes exceeds limit of {MAX_FILE_SIZE_BYTES} bytes."
        if file_size > 0:
            chunk = path.open("rb").read(BINARY_DETECTION_CHUNK_SIZE)
            if b'\x00' in chunk:
                return "File contains null bytes, indicating it is likely binary."
    except OSError as e:
        return f"Cannot access file properties: {e}"
    return None


def _read_file_with_encoding_detection(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Надежно читает текстовый файл, используя гибридный подход к определению кодировки."""
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        logging.warning(f"File '{path}' is not UTF-8. Detecting encoding...")
        try:
            raw_data = path.read_bytes()
            if not raw_data: return "", None
            detected = chardet.detect(raw_data)
            encoding = detected.get("encoding")
            confidence = detected.get("confidence", 0)
            if encoding and confidence > 0.7:
                logging.info(f"Chardet detected encoding '{encoding}' with confidence {confidence:.0%}")
                return raw_data.decode(encoding), None
            else:
                error_msg = f"Could not reliably detect encoding (guess: {encoding}, confidence: {confidence:.0%})"
                logging.error(f"Error for file '{path}': {error_msg}")
                return None, error_msg
        except Exception as e:
            error_msg = f"Critical error during reading and decoding: {e}"
            logging.error(f"Error for file '{path}': {error_msg}", exc_info=True)
            return None, error_msg
    except Exception as e:
        error_msg = f"Failed to read file: {e}"
        logging.error(f"Error for file '{path}': {error_msg}", exc_info=True)
        return None, error_msg


class SyncWorker(QObject):
    """
    Управляет соединением с Socket.IO сервером и обработкой событий.
    Предназначен для запуска в отдельном QThread.
    """
    status_changed = pyqtSignal(str, str)
    connection_error = pyqtSignal(str)
    registered = pyqtSignal(dict)
    update_requested = pyqtSignal(str)

    def __init__(self, client_data: Dict[str, str], gitignore_filter: GitignoreFilter, parent: QObject | None = None):
        super().__init__(parent)
        self._client_data = client_data
        self._gitignore_filter = gitignore_filter
        self._is_running = True
        self._http_session = requests.Session()
        self._sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=RECONNECT_DELAY_SECONDS,
            reconnection_delay_max=RECONNECT_DELAY_MAX_SECONDS,
            http_session=self._http_session,
            logger=True,
            engineio_logger=True
        )
        self._register_sio_events()

    def _check_proxy_and_get_config(self) -> Tuple[str, Optional[Dict[str, str]]]:
        """Проверяет работоспособность SOCKS5 прокси и возвращает URL и конфиг для requests."""
        proxies = {'http': SOCKS_PROXY_URL, 'https': SOCKS_PROXY_URL}
        try:
            logging.info(f"Проверка SOCKS5 прокси по адресу {SOCKS_PROXY_URL}...")
            response = requests.get(PROXY_TEST_URL, proxies=proxies, timeout=PROXY_TEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            logging.info("SOCKS5 прокси работает. Используется HTTP-соединение через прокси.")
            return HTTP_URL_VIA_PROXY, proxies
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logging.warning(f"SOCKS5 прокси недоступен, используется прямое HTTPS-соединение. Причина: {type(e).__name__}")
            return HTTPS_URL_DIRECT, None
        except Exception as e:
            logging.error(f"Неожиданная ошибка при проверке прокси: {e}")
            logging.warning("Прокси недоступен, используется прямое HTTPS-соединение.")
            return HTTPS_URL_DIRECT, None

    def _register_sio_events(self) -> None:
        sio = self._sio
        sio.on("connect", namespace=CLIENT_NAMESPACE, handler=self._on_connect)
        sio.on("disconnect", namespace=CLIENT_NAMESPACE, handler=self._on_disconnect)
        sio.on("connect_error", handler=self._on_connect_error)
        sio.on("update_files", namespace=CLIENT_NAMESPACE, handler=self._on_update_files)
        sio.on("get_file_tree", namespace=CLIENT_NAMESPACE, handler=self._on_get_file_tree)
        sio.on("get_file_content", namespace=CLIENT_NAMESPACE, handler=self._on_get_file_content)

    def run(self) -> None:
        logging.info(f"Воркер запущен. Client ID: '{self._client_data['id']}'")
        while self._is_running:
            try:
                server_url, proxies = self._check_proxy_and_get_config()
                self._http_session.proxies = proxies or {}
                self.status_changed.emit("Подключение...", "connecting")
                self._sio.connect(
                    server_url,
                    namespaces=[CLIENT_NAMESPACE],
                    transports=['polling'],
                    wait_timeout=CONNECTION_TIMEOUT_SECONDS,
                )
                self._sio.wait()
            except socketio.exceptions.ConnectionError as e:
                if self._is_running:
                    logging.error(f"Не удалось подключиться к серверу: {e}")
                    self.connection_error.emit(str(e) or "Не удалось подключиться")
            except Exception as e:
                if self._is_running:
                    logging.critical(f"Критическая ошибка в цикле воркера: {e}", exc_info=True)
                    self.connection_error.emit("Критическая ошибка")
            finally:
                if self._sio.connected:
                    self._sio.disconnect()
            if self._is_running:
                logging.info(f"Следующая попытка подключения через {RECONNECT_DELAY_SECONDS} секунд...")
                time.sleep(RECONNECT_DELAY_SECONDS)
        logging.info("Цикл воркера завершен.")

    def stop(self) -> None:
        logging.info("Получен сигнал остановки для воркера.")
        self._is_running = False
        if self._sio.connected:
            self._sio.disconnect()
        self._sio.shutdown()
        logging.info("Остановка воркера инициирована.")

    def manual_reconnect(self) -> None:
        logging.info("Запрошено ручное переподключение. Отключаемся...")
        if self._sio.connected:
            self._sio.disconnect()

    def _on_connect(self) -> None:
        transport = self._sio.transport()
        status_text = f"Подключен (sid: {self._sio.sid}, transport: {transport})"
        self.status_changed.emit(status_text, "connected")
        logging.info(f"Успешно подключен (sid={self._sio.sid}, transport={transport})")
        logging.info(f"Регистрация на сервере с данными: {self._client_data}")
        self._sio.emit("register", self._client_data, namespace=CLIENT_NAMESPACE)
        self.registered.emit(self._client_data)

    def _on_disconnect(self) -> None:
        logging.warning("Отключен от сервера. Библиотека начнет автоматическое переподключение...")
        self.status_changed.emit("Переподключение...", "disconnected")

    def _on_connect_error(self, data: Any) -> None:
        logging.error(f"Ошибка подключения от сервера: {data}")
        self.connection_error.emit(str(data))

    def _on_update_files(self, data: Dict[str, Any]) -> None:
        files: List[Dict[str, str]] = data.get("files", [])
        if not isinstance(files, list) or not files:
            logging.warning("Получена команда update_files, но список файлов пуст или невалиден.")
            return
        logging.info(f"Получен запрос на обновление {len(files)} файлов. Передача в основной поток...")
        try:
            files_json = json.dumps(files)
            self.update_requested.emit(files_json)
        except TypeError as e:
            logging.error(f"Не удалось сериализовать данные файлов в JSON: {e}")

    def _on_get_file_tree(self, data: Dict[str, Any]) -> None:
        # _CHANGED_: Возвращаем логику обработки `request_id`
        request_id = data.get("request_id")
        if not request_id:
            logging.warning("Получен запрос get_file_tree без request_id.")
            return
        logging.info(f"Получен запрос на дерево файлов (req_id: {request_id}).")
        try:
            file_list = []
            for path in ROOT_DIR.rglob("*"):
                if self._gitignore_filter.is_ignored(path):
                    continue
                if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT_DIR).parts):
                    continue
                if path.is_file():
                    if _is_file_unsuitable_for_sync(path) is None:
                        relative_path = path.relative_to(ROOT_DIR).as_posix()
                        file_list.append(relative_path)
            response = {"request_id": request_id, "payload": {"files": file_list}}
            self._sio.emit("file_tree_response", response, namespace=CLIENT_NAMESPACE)
            logging.info(f"Отправлен ответ на дерево файлов с {len(file_list)} файлами.")
        except Exception as e:
            logging.error(f"Ошибка при сборке дерева файлов: {e}", exc_info=True)
            response = {"request_id": request_id, "payload": {"error": f"Ошибка на стороне клиента: {e}"}}
            self._sio.emit("file_tree_response", response, namespace=CLIENT_NAMESPACE)

    def _on_get_file_content(self, data: Dict[str, Any]) -> None:
        # _CHANGED_: Возвращаем логику обработки `request_id`
        request_id = data.get("request_id")
        paths_to_read = data.get("paths", [])
        if not request_id:
            logging.warning("Получен запрос get_file_content без request_id.")
            return
        logging.info(f"Получен запрос на содержимое {len(paths_to_read)} файлов (req_id: {request_id}).")
        files_with_content = []
        root_dir_str = str(ROOT_DIR.resolve())
        try:
            for rel_path_str in paths_to_read:
                try:
                    full_path = (ROOT_DIR / rel_path_str).resolve()
                    if not str(full_path).startswith(root_dir_str):
                         raise SecurityException(f"Попытка доступа за пределы ROOT_DIR: {rel_path_str}")
                    if self._gitignore_filter.is_ignored(full_path):
                        skip_reason = "Файл игнорируется .gitignore"
                        logging.warning(f"Пропуск файла '{rel_path_str}': {skip_reason}")
                        files_with_content.append({"path": rel_path_str, "content": None, "error": skip_reason})
                        continue
                    if not full_path.is_file():
                        files_with_content.append({"path": rel_path_str, "content": None, "error": "Файл не найден или не является обычным файлом."})
                        continue
                    skip_reason = _is_file_unsuitable_for_sync(full_path)
                    if skip_reason:
                        logging.info(f"Пропуск файла '{rel_path_str}': {skip_reason}")
                        files_with_content.append({"path": rel_path_str, "content": None, "error": skip_reason})
                        continue
                    content, error = _read_file_with_encoding_detection(full_path)
                    files_with_content.append({"path": rel_path_str, "content": content, "error": error})
                except SecurityException as e:
                    logging.error(f"[БЕЗОПАСНОСТЬ] {e}")
                    files_with_content.append({"path": rel_path_str, "content": None, "error": str(e)})
                except Exception as e:
                    logging.error(f"Не удалось обработать путь '{rel_path_str}': {e}")
                    files_with_content.append({"path": rel_path_str, "content": None, "error": str(e)})
            response = {"request_id": request_id, "payload": {"files": files_with_content}}
            self._sio.emit("file_content_response", response, namespace=CLIENT_NAMESPACE)
            logging.info(f"Отправлен ответ с содержимым {len(files_with_content)} файлов.")
        except Exception as e:
            logging.error(f"Критическая ошибка при обработке запроса на содержимое файлов: {e}", exc_info=True)
            response = {"request_id": request_id, "payload": {"error": f"Критическая ошибка на стороне клиента: {e}"}}
            self._sio.emit("file_content_response", response, namespace=CLIENT_NAMESPACE)