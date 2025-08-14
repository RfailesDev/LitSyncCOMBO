# web/api.py
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request
from flask_socketio import SocketIO

from config import TEST_SAVE_ENABLED, TEST_SAVE_PATH
from core.change_detector import ChangeDetector, FileChange
from core.clients import ClientRegistry
from core.context7 import APIError, RateLimitError
from core.parser import LLMResponseParserV7
from core.prompt_builder import PromptBuilder
from core.request_coordinator import RequestCoordinator

logger = logging.getLogger(__name__)


def create_api_blueprint(
        registry: ClientRegistry,
        parser: LLMResponseParserV7,
        sio: SocketIO,
        coordinator: RequestCoordinator,
        prompt_builder: PromptBuilder,
        change_detector: ChangeDetector,
) -> Blueprint:
    """Фабрика для создания основного API Blueprint с внедренными зависимостями."""
    api_bp = Blueprint("api", __name__, url_prefix="/api")

    def _save_raw_text_for_debugging(text: str, client_sid: str) -> None:
        if not TEST_SAVE_ENABLED:
            return
        try:
            os.makedirs(TEST_SAVE_PATH, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_sid = "".join(c for c in client_sid if c.isalnum())
            filename = f"{timestamp}_{safe_sid}.txt"
            filepath = os.path.join(TEST_SAVE_PATH, filename)
            with open(filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            logger.info(f"Отладочный файл сохранен: {filepath}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении отладочного файла: {e}", exc_info=True)

    @api_bp.route("/clients", methods=["GET"])
    def get_clients_api():
        return jsonify(registry.get_all_registered())

    @api_bp.route("/sync", methods=["POST"])
    def sync_files_api():
        data = request.get_json()
        if not data or "clientId" not in data or "text" not in data:
            return jsonify({"error": "Некорректный запрос. Отсутствуют поля 'clientId' или 'text'."}), 400

        client_sid: str = data["clientId"]
        raw_llm_text: str = data["text"]
        _save_raw_text_for_debugging(raw_llm_text, client_sid)

        if not registry.is_present(client_sid):
            return jsonify({"error": "Клиент не найден или уже отключился."}), 404

        llm_text = raw_llm_text.replace('\r\n', '\n')
        client_hostname = registry.get_hostname(client_sid)
        logger.info(f"Получен запрос на СИНХРОНИЗАЦИЮ для клиента: {client_hostname} ({client_sid})")

        try:
            files_to_update, debug_info = parser.parse(llm_text)
            if not files_to_update:
                logger.warning(f"Парсер не извлек файлы для клиента {client_sid}. Отправка ответа об ошибке.")
                return jsonify({
                    "error": "Не удалось извлечь ни одной пары 'файл-код' из текста. Убедитесь, что путь к файлу указан на отдельной строке прямо перед блоком кода.",
                    "debug_info": debug_info
                }), 400

            sio.emit(
                "update_files",
                {"files": files_to_update},
                namespace="/client",
                to=client_sid,
            )
            logger.info(f"Команда на обновление {len(files_to_update)} файлов успешно отправлена клиенту {client_sid}")
            return jsonify(
                {
                    "status": "success",
                    "message": f"Команда на обновление {len(files_to_update)} файлов отправлена.",
                    "files_sent": len(files_to_update),
                }
            )
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке запроса на синхронизацию: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса."}), 500

    @api_bp.route("/sync/preview", methods=["POST"])
    def sync_preview_api():
        data = request.get_json()
        if not data or "clientId" not in data or "text" not in data:
            return jsonify({"error": "Некорректный запрос."}), 400

        client_sid: str = data["clientId"]
        raw_llm_text: str = data["text"]

        if not registry.is_present(client_sid):
            return jsonify({"error": "Клиент не найден или отключился."}), 404

        client_hostname = registry.get_hostname(client_sid)
        logger.info(f"Получен запрос на ПРЕДПРОСМОТР для клиента: {client_hostname} ({client_sid})")

        try:
            llm_text = raw_llm_text.replace('\r\n', '\n')
            new_files_content, _ = parser.parse(llm_text)
            if not new_files_content:
                return jsonify({"error": "Не удалось извлечь файлы из текста для предпросмотра."}), 400

            paths_to_check = [file["path"] for file in new_files_content]

            logger.info(f"Запрос текущего содержимого {len(paths_to_check)} файлов у клиента {client_sid}")
            response = coordinator.make_request(
                client_sid, "get_file_content", {"paths": paths_to_check}
            )

            if response.get("error"):
                return jsonify({"error": f"Ошибка на клиенте: {response['error']}"}), 502

            current_files_content = {
                file["path"]: file for file in response.get("files", [])
            }

            changes: List[FileChange] = []
            for new_file in new_files_content:
                path = new_file["path"]
                new_content = new_file["content"]
                current_file = current_files_content.get(path)

                if not current_file or current_file.get("content") is None:
                    hunks = change_detector.generate_diff("", new_content)
                    changes.append({
                        "path": path,
                        "status": "added",
                        "hunks": hunks,
                        "error_message": current_file.get("error") if current_file else None
                    })
                else:
                    old_content = current_file["content"]
                    hunks = change_detector.generate_diff(old_content, new_content)
                    changes.append({
                        "path": path,
                        "status": "modified",
                        "hunks": hunks,
                        "error_message": None
                    })

            logger.info(f"Сгенерирован diff для {len(changes)} файлов. Отправка в расширение.")
            return jsonify({"changes": changes})

        except TimeoutError:
            return jsonify({"error": "Клиент не ответил на запрос о содержимом файлов вовремя."}), 504
        except Exception as e:
            logger.error(f"Критическая ошибка при генерации предпросмотра: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера при генерации предпросмотра."}), 500

    @api_bp.route("/clients/<string:client_sid>/file_tree", methods=["GET"])
    def get_file_tree_api(client_sid: str):
        if not registry.is_present(client_sid):
            return jsonify({"error": "Клиент не найден или отключился."}), 404
        try:
            # Этот эндпоинт теперь снова блокирующий и возвращает результат напрямую.
            response = coordinator.make_request(client_sid, "get_file_tree")
            return jsonify(response)
        except TimeoutError:
            return jsonify({"error": "Клиент не ответил на запрос вовремя."}), 504
        except Exception as e:
            logger.error(f"Ошибка при запросе дерева файлов у {client_sid}: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера."}), 500

    @api_bp.route("/clients/<string:client_sid>/file_content", methods=["POST"])
    def get_file_content_api(client_sid: str):
        if not registry.is_present(client_sid):
            return jsonify({"error": "Клиент не найден или отключился."}), 404
        data = request.get_json()
        paths = data.get("paths")
        if not isinstance(paths, list):
            return jsonify({"error": "Поле 'paths' должно быть списком."}), 400
        try:
            response = coordinator.make_request(
                client_sid, "get_file_content", {"paths": paths}
            )
            return jsonify(response)
        except TimeoutError:
            return jsonify({"error": "Клиент не ответил на запрос вовремя."}), 504
        except Exception as e:
            logger.error(f"Ошибка при запросе контента у {client_sid}: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера."}), 500

    @api_bp.route("/prompt/generate", methods=["POST"])
    def generate_prompt_api():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Пустое тело запроса."}), 400

        files = data.get("files")
        client_sid = data.get("clientId")
        docs = data.get("docs")

        if not isinstance(files, list):
            return jsonify({"error": "Поле 'files' должно быть списком."}), 400
        if not client_sid:
            return jsonify({"error": "Не предоставлен 'clientId'."}), 400
        if docs and not isinstance(docs, list):
            return jsonify({"error": "Поле 'docs' должно быть списком."}), 400

        try:
            client_meta = registry.get_client_metadata(client_sid)
            if not client_meta:
                root_name = "unknown_project"
                logger.warning(f"Не найдены метаданные для клиента {client_sid}, используется имя по умолчанию.")
            else:
                root_name = client_meta.get("root_dir_name", "project")

            prompt_text = prompt_builder.build(files, root_name=root_name, docs=docs)
            return jsonify({"prompt": prompt_text})
        except Exception as e:
            logger.error(f"Ошибка при генерации промпта: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера при генерации промпта."}), 500

    return api_bp


def create_context7_api_blueprint() -> Blueprint:
    """Фабрика для создания API Blueprint для проксирования запросов к Context7."""
    context7_bp = Blueprint("context7_api", __name__, url_prefix="/api/context7")

    @context7_bp.route("/search", methods=["GET"])
    def search_docs():
        from app import get_context7_client

        query = request.args.get("query")
        if not query:
            return jsonify({"error": "Параметр 'query' обязателен."}), 400
        try:
            client = get_context7_client()
            logger.info(f"Выполняется поиск в Context7 по запросу: '{query}'")
            search_response = client.search(query)
            return jsonify(search_response.model_dump(by_alias=True))
        except RateLimitError as e:
            logger.warning(f"Достигнут лимит запросов к Context7 API: {e}")
            return jsonify({"error": "Сервер временно перегружен запросами к базе знаний. Попробуйте позже."}), 429
        except APIError as e:
            logger.error(f"Ошибка API Context7 при поиске: {e}", exc_info=True)
            return jsonify({"error": "Ошибка при взаимодействии с базой знаний."}), 502
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при поиске в Context7: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера."}), 500

    @context7_bp.route("/docs/<path:library_id>", methods=["GET"])
    def get_doc_content(library_id: str):
        from app import get_context7_client

        topic = request.args.get("topic")
        try:
            client = get_context7_client()
            logger.info(f"Запрос документации из Context7 для ID: '{library_id}'")
            content = client.fetch_documentation(library_id, topic=topic)
            if content is None:
                return jsonify({"error": "Документация не найдена."}), 404
            return jsonify({"id": library_id, "content": content})
        except RateLimitError as e:
            logger.warning(f"Достигнут лимит запросов к Context7 API: {e}")
            return jsonify({"error": "Сервер временно перегружен запросами к базе знаний. Попробуйте позже."}), 429
        except APIError as e:
            logger.error(f"Ошибка API Context7 при получении документации: {e}", exc_info=True)
            return jsonify({"error": "Ошибка при взаимодействии с базой знаний."}), 502
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при получении документации из Context7: {e}", exc_info=True)
            return jsonify({"error": "Внутренняя ошибка сервера."}), 500

    return context7_bp