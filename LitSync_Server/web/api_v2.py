# web/api_v2.py
import logging
from typing import Any, Dict, List, Optional

from quart import Blueprint, jsonify, request

from core.clients import ClientRegistry
from core.request_coordinator import RequestCoordinator

logger = logging.getLogger(__name__)


# Команды для polling клиента используют такой формат:
# {
#   "type": "get_file_tree" | "get_file_content" | "update_files",
#   "request_id": "uuid",
#   "payload": { ... },
#   "upload_url": "https://domain/v2/upload/<sid>/<req_id>"  # для больших данных, если требуется
# }


def create_v2_blueprint(*, registry: ClientRegistry, coordinator: RequestCoordinator) -> Blueprint:
    v2_bp = Blueprint("api_v2", __name__, url_prefix="/v2")

    @v2_bp.post("/register")
    async def v2_register():
        data = await request.get_json()
        client_id = (data or {}).get("id")
        root_dir_name = (data or {}).get("root_dir_name", "project")
        if not client_id:
            return jsonify({"error": "Отсутствует 'id'"}), 400
        # В polling режиме мы фиксируем фиктивный sid = client_id (не пересекается с socketio sid)
        # и регистрируем его в общей таблице
        sid = client_id
        registry.add(sid=sid, ip="polling")
        registry.register(sid=sid, data={"id": client_id, "root_dir_name": root_dir_name})
        logger.info(f"Polling клиент зарегистрирован: {client_id}")
        return jsonify({"clientId": sid})

    @v2_bp.post("/disconnect")
    async def v2_disconnect():
        data = await request.get_json()
        sid = (data or {}).get("clientId")
        if sid:
            registry.remove(sid)
            logger.info(f"Polling клиент отключен: {sid}")
        return jsonify({"status": "ok"})

    @v2_bp.get("/check")
    async def v2_check():
        sid = request.args.get("clientId")
        if not sid:
            return jsonify({"error": "clientId is required"}), 400
        if not registry.is_present(sid):
            return jsonify({"error": "unknown client"}), 404
        commands = await coordinator.fetch_polling_commands(sid)
        return jsonify({"commands": commands})

    @v2_bp.post("/upload/<string:sid>/<string:req_id>")
    async def v2_upload(sid: str, req_id: str):
        # Клиент присылает большие данные (например, содержимое нескольких файлов)
        # Формат: { "payload": { ... } }
        data = await request.get_json()
        if not data or "payload" not in data:
            return jsonify({"error": "payload is required"}), 400
        # Пробрасываем как будто это ответ на запрос с данным req_id
        await coordinator.handle_response(sid, {"request_id": req_id, "payload": data["payload"]})
        return jsonify({"status": "received"})

    return v2_bp