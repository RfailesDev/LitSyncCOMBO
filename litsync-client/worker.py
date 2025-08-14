# worker.py
"""
Сетевой воркер для LitSync-Client.
Финальная, стабильная версия.
- Логика подключения полагается на встроенные механизмы библиотеки.
- Обработчики событий соответствуют RPC-протоколу сервера.
- Добавлен альтернативный режим Polling через /v2 API для обхода DPI.
"""
import json
import logging
import time
import threading
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
                    SOCKS_PROXY_URL, PROXY_TEST_URL, PROXY_TEST_TIMEOUT_SECONDS,
                    USE_POLLING_MODE, USE_PROXY, POLLING_INTERVAL_SECONDS)
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
    В режиме Polling полностью отключает Socket.IO и использует /v2 API.
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
        self._server_url: str = HTTPS_URL_DIRECT
        self._proxies: Optional[Dict[str, str]] = None
        self._client_sid: Optional[str] = None

        # SocketIO client (используется только когда USE_POLLING_MODE = False)
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
        if not USE_PROXY:
            logging.info("USE_PROXY=False: принудительное отключение прокси, используется прямое HTTPS-соединение.")
            return HTTPS_URL_DIRECT, None
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
        logging.info(f"Воркер запущен. Client ID: '{self._client_data['id']}' (polling={USE_POLLING_MODE})")
        while self._is_running:
            try:
                self._server_url, self._proxies = self._check_proxy_and_get_config()
                self._http_session.proxies = self._proxies or {}
                if USE_POLLING_MODE:
                    self._run_polling_loop()
                else:
                    self._run_socketio_loop()
            except Exception as e:
                if self._is_running:
                    logging.critical(f"Критическая ошибка в цикле воркера: {e}", exc_info=True)
                    self.connection_error.emit("Критическая ошибка")
            finally:
                if not USE_POLLING_MODE and self._sio.connected:
                    self._sio.disconnect()
            if self._is_running and not USE_POLLING_MODE:
                logging.info(f"Следующая попытка подключения через {RECONNECT_DELAY_SECONDS} секунд...")
                time.sleep(RECONNECT_DELAY_SECONDS)
        logging.info("Цикл воркера завершен.")

    def _run_socketio_loop(self) -> None:
        self.status_changed.emit("Подключение...", "connecting")
        self._sio.connect(
            self._server_url,
            namespaces=[CLIENT_NAMESPACE],
            wait_timeout=CONNECTION_TIMEOUT_SECONDS,
        )
        self._sio.wait()

    def _run_polling_loop(self) -> None:
        # Регистрация
        try:
            self.status_changed.emit("Регистрация (polling)...", "connecting")
            resp = self._http_session.post(f"{self._server_url}/v2/register", json={
                "id": self._client_data["id"],
                "root_dir_name": self._client_data.get("root_dir_name", "project")
            }, timeout=10)
            resp.raise_for_status()
            self._client_sid = resp.json().get("clientId")
            self.registered.emit(self._client_data)
            self.status_changed.emit(f"Подключен (polling), clientId={self._client_sid}", "connected")
            logging.info(f"Polling режим активен. clientId={self._client_sid}")
        except Exception as e:
            logging.error(f"Не удалось зарегистрироваться в polling режиме: {e}")
            self.connection_error.emit("Регистрация polling не удалась")
            time.sleep(RECONNECT_DELAY_SECONDS)
            return

        try:
            while self._is_running:
                try:
                    check = self._http_session.get(f"{self._server_url}/v2/check", params={"clientId": self._client_sid}, timeout=10)
                    check.raise_for_status()
                    commands: List[Dict[str, Any]] = check.json().get("commands", [])
                    for cmd in commands:
                        self._handle_polling_command(cmd)
                except Exception as e:
                    logging.error(f"Ошибка polling-запроса /v2/check: {e}")
                    self.status_changed.emit("Потеря соединения (polling). Переподключение...", "disconnected")
                    time.sleep(RECONNECT_DELAY_SECONDS)
                time.sleep(POLLING_INTERVAL_SECONDS)
        finally:
            # Грейсфул отключение
            try:
                self._http_session.post(f"{self._server_url}/v2/disconnect", json={"clientId": self._client_sid}, timeout=5)
            except Exception:
                pass

    def _handle_polling_command(self, cmd: Dict[str, Any]) -> None:
        cmd_type = cmd.get("type")
        request_id = cmd.get("request_id")
        payload = cmd.get("payload", {})
        upload_url = cmd.get("upload_url")
        if cmd_type == "update_files":
            files: List[Dict[str, str]] = payload.get("files", [])
            try:
                files_json = json.dumps(files)
                self.update_requested.emit(files_json)
            except TypeError as e:
                logging.error(f"Не удалось сериализовать данные файлов в JSON: {e}")
        elif cmd_type == "get_file_tree":
            file_list = []
            try:
                for path in ROOT_DIR.rglob("*"):
                    if self._gitignore_filter.is_ignored(path):
                        continue
                    if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT_DIR).parts):
                        continue
                    if path.is_file():
                        if _is_file_unsuitable_for_sync(path) is None:
                            relative_path = path.relative_to(ROOT_DIR).as_posix()
                            file_list.append(relative_path)
                self._upload_polling_response(upload_url, request_id, {"files": file_list})
            except Exception as e:
                logging.error(f"Ошибка при сборке дерева файлов (polling): {e}")
                self._upload_polling_response(upload_url, request_id, {"error": str(e)})
        elif cmd_type == "get_file_content":
            paths_to_read: List[str] = payload.get("paths", [])
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
                self._upload_polling_response(upload_url, request_id, {"files": files_with_content})
            except Exception as e:
                logging.error(f"Критическая ошибка при обработке запроса на содержимое файлов (polling): {e}", exc_info=True)
                self._upload_polling_response(upload_url, request_id, {"error": str(e)})
        else:
            logging.warning(f"Неизвестная команда (polling): {cmd}")

    def _upload_polling_response(self, upload_url: Optional[str], request_id: Optional[str], payload: Dict[str, Any]) -> None:
        if not upload_url:
            logging.error(f"Нет upload_url для отправки ответа (req_id={request_id}).")
            return
        try:
            # Используем отдельный HTTP вызов (без общей с Socket.IO сессии), чтобы исключить блокировки/гонки
            resp = requests.post(upload_url, json={"payload": payload}, timeout=60, proxies=self._proxies or {})
            resp.raise_for_status()
            logging.info(f"Успешно отправлен ответ на {upload_url} (req_id: {request_id})")
        except Exception as e:
            logging.error(f"Не удалось отправить ответ на {upload_url}: {e}")

    def stop(self) -> None:
        logging.info("Получен сигнал остановки для воркера.")
        self._is_running = False
        if USE_POLLING_MODE:
            # В polling режиме остановка произойдет в основном цикле, здесь ничего не делаем
            return
        if self._sio.connected:
            self._sio.disconnect()
        self._sio.shutdown()
        logging.info("Остановка воркера инициирована.")

    def manual_reconnect(self) -> None:
        logging.info("Запрошено ручное переподключение. Отключаемся...")
        if not USE_POLLING_MODE and self._sio.connected:
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
        # _CHANGED_: Обработка переносится в фон, чтобы не блокировать PONG
        request_id = data.get("request_id")
        upload_url = data.get("upload_url")
        if not request_id:
            logging.warning("Получен запрос get_file_tree без request_id.")
            return
        logging.info(f"Получен запрос на дерево файлов (req_id: {request_id}). Запускаю фоновую обработку...")
        threading.Thread(
            target=self._process_get_file_tree,
            args=(request_id, upload_url),
            daemon=True,
        ).start()

    def _process_get_file_tree(self, request_id: str, upload_url: Optional[str]) -> None:
        try:
            file_list: List[str] = []
            for path in ROOT_DIR.rglob("*"):
                if self._gitignore_filter.is_ignored(path):
                    continue
                if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT_DIR).parts):
                    continue
                if path.is_file():
                    if _is_file_unsuitable_for_sync(path) is None:
                        relative_path = path.relative_to(ROOT_DIR).as_posix()
                        file_list.append(relative_path)
            payload = {"files": file_list}
            if upload_url:
                self._upload_polling_response(upload_url, request_id, payload)
            else:
                response = {"request_id": request_id, "payload": payload}
                self._sio.emit("file_tree_response", response, namespace=CLIENT_NAMESPACE)
            logging.info(f"Отправлен ответ на дерево файлов с {len(file_list)} файлами (req_id: {request_id}).")
        except Exception as e:
            logging.error(f"Ошибка при сборке дерева файлов: {e}", exc_info=True)
            payload = {"error": f"Ошибка на стороне клиента: {e}"}
            if upload_url:
                self._upload_polling_response(upload_url, request_id, payload)
            else:
                response = {"request_id": request_id, "payload": payload}
                self._sio.emit("file_tree_response", response, namespace=CLIENT_NAMESPACE)

    def _on_get_file_content(self, data: Dict[str, Any]) -> None:
        # _CHANGED_: Обработка переносится в фон, чтобы не блокировать PONG
        request_id = data.get("request_id")
        upload_url = data.get("upload_url")
        paths_to_read = data.get("paths", [])
        if not request_id:
            logging.warning("Получен запрос get_file_content без request_id.")
            return
        logging.info(f"Получен запрос на содержимое {len(paths_to_read)} файлов (req_id: {request_id}). Запускаю фоновую обработку...")
        threading.Thread(
            target=self._process_get_file_content,
            args=(request_id, upload_url, paths_to_read),
            daemon=True,
        ).start()

    def _process_get_file_content(self, request_id: str, upload_url: Optional[str], paths_to_read: List[str]) -> None:
        files_with_content: List[Dict[str, Optional[str]]] = []
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
            payload = {"files": files_with_content}
            if upload_url:
                self._upload_polling_response(upload_url, request_id, payload)
            else:
                response = {"request_id": request_id, "payload": payload}
                self._sio.emit("file_content_response", response, namespace=CLIENT_NAMESPACE)
            logging.info(f"Отправлен ответ с содержимым {len(files_with_content)} файлов (req_id: {request_id}).")
        except Exception as e:
            logging.error(f"Критическая ошибка при обработке запроса на содержимое файлов: {e}", exc_info=True)
            payload = {"error": f"Критическая ошибка на стороне клиента: {e}"}
            if upload_url:
                self._upload_polling_response(upload_url, request_id, payload)
            else:
                response = {"request_id": request_id, "payload": payload}
                self._sio.emit("file_content_response", response, namespace=CLIENT_NAMESPACE)