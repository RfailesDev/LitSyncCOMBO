# client.py
"""
LitSync-Client: Консольный клиент для синхронизации файлов с GUI-уведомлениями.

Версия 4.0.0:
- Приложение переведено в консольный режим. GUI-окно удалено.
- Сохранены критически важные GUI-элементы: QSystemTrayIcon и QMessageBox.
- Добавлена поддержка Long-Polling для стабильности соединения.
- Реализована автоматическая проверка и использование SOCKS5 прокси.
"""
import json
import logging
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple

from PyQt6.QtCore import QThread
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu

from config import APP_NAME, APP_VERSION, EXCLUDED_DIRS, ROOT_DIR
from pathfilter import GitignoreFilter
from worker import SyncWorker

# --- Настройка Логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


class UpdateStats(NamedTuple):
    success: int = 0
    failed: int = 0
    skipped: int = 0


class LitSyncApp:
    """
    Основной класс приложения. Управляет жизненным циклом, воркером и GUI-элементами.
    Работает в консоли, но использует QApplication для поддержки трея и диалогов.
    """
    def __init__(self, argv: List[str]):
        self.app = QApplication(argv)
        # Приложение не должно завершаться, если последний видимый виджет (диалог) закрылся.
        # Мы управляем выходом вручную.
        self.app.setQuitOnLastWindowClosed(False)

        # --- Основные компоненты ---
        self._project_name = ROOT_DIR.name
        self._gitignore_filter = GitignoreFilter(ROOT_DIR)
        self._client_data = self._create_client_identifier()

        # --- Трей и Воркер ---
        self._tray_icon = self._setup_tray_icon()
        self._worker_thread = QThread()
        self._worker_thread.setObjectName("SyncWorkerThread")
        self._worker = self._setup_worker()

        # --- Связывание сигналов ---
        self._connect_signals()

        # Сигналы завершения работы
        self.app.aboutToQuit.connect(self._worker.stop)
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

        logging.info(f"--- {APP_NAME} v{APP_VERSION} ---")
        logging.info(f"Корневая директория проекта определена как: {ROOT_DIR}")
        logging.info(f"Сгенерированный ID клиента: {self._client_data['id']}")
        logging.info("Приложение запущено. Используйте иконку в трее для управления.")

    def run(self) -> int:
        """Запускает event loop приложения."""
        self._worker_thread.start()
        return self.app.exec()

    def _handle_exit(self, sig, frame):
        """Обработчик системных сигналов для корректного выхода."""
        logging.info(f"Получен сигнал {sig}, инициирую выход...")
        self.app.quit()

    def _connect_signals(self):
        """Централизованное подключение всех сигналов и слотов."""
        # Сигналы от воркера к приложению
        self._worker.status_changed.connect(self._on_worker_status_changed)
        self._worker.connection_error.connect(self._on_worker_connection_error)
        self._worker.update_requested.connect(self._on_update_requested)
        self._worker.registered.connect(self._on_worker_registered)

    def _count_project_files(self) -> int:
        """Подсчитывает количество файлов в проекте, учитывая .gitignore и EXCLUDED_DIRS."""
        count = 0
        for p in ROOT_DIR.rglob('*'):
            if self._gitignore_filter.is_ignored(p):
                continue
            if any(part in EXCLUDED_DIRS for part in p.relative_to(ROOT_DIR).parts):
                continue
            if p.is_file():
                count += 1
        return count

    def _create_client_identifier(self) -> Dict[str, str]:
        """Создает уникальный идентификатор и собирает метаданные клиента."""
        try:
            file_count = self._count_project_files()
        except Exception as e:
            logging.error(f"Не удалось посчитать файлы: {e}")
            file_count = "err"
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "unknown-host"

        client_id = f"{self._project_name}-{file_count}-{hostname}"

        return {
            "id": client_id,
            "root_dir_name": self._project_name
        }

    def _setup_tray_icon(self) -> QSystemTrayIcon:
        """Настраивает иконку и меню в системном трее."""
        # Попытка найти иконку. Если ее нет, PyQt создаст стандартную.
        icon_path = Path(__file__).parent / "icon.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        tray = QSystemTrayIcon(icon, self.app)
        tray.setToolTip(f"{APP_NAME} - Инициализация...")

        menu = QMenu()
        # Кнопка для ручного переподключения
        reconnect_action = QAction("Переподключиться", self.app)
        reconnect_action.triggered.connect(self._on_reconnect_clicked)
        menu.addAction(reconnect_action)
        menu.addSeparator()
        # Кнопка выхода
        quit_action = QAction("Выход", self.app)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        tray.show()
        return tray

    def _setup_worker(self) -> SyncWorker:
        """Создает и настраивает экземпляр воркера."""
        worker = SyncWorker(client_data=self._client_data, gitignore_filter=self._gitignore_filter)
        worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(worker.run)
        return worker

    def _on_worker_status_changed(self, status_text: str, state_key: str):
        """Обновляет статус в консоли и в тултипе трея."""
        logging.info(f"Статус: {status_text}")
        tooltip = f"{APP_NAME} - {status_text}"
        self._tray_icon.setToolTip(tooltip)

    def _on_worker_connection_error(self, error_msg: str):
        """Обрабатывает ошибки подключения."""
        status_text = f"Ошибка: {error_msg}"
        logging.error(status_text)
        self._tray_icon.setToolTip(f"{APP_NAME} - {status_text}")

    def _on_worker_registered(self, data: dict):
        """Показывает системное уведомление об успешной регистрации."""
        msg = f"Клиент зарегистрирован на сервере как '{data['id']}'"
        self._tray_icon.showMessage("Успешная регистрация", msg, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _on_reconnect_clicked(self):
        """Обрабатывает нажатие кнопки 'Переподключиться' в меню трея."""
        logging.warning("Ручной запуск переподключения...")
        self._worker.manual_reconnect()

    def _on_update_requested(self, files_json: str):
        """Показывает модальный диалог подтверждения обновления."""
        try:
            files: List[Dict[str, str]] = json.loads(files_json)
            if not files:
                logging.warning("Получен пустой список файлов для обновления.")
                return
        except json.JSONDecodeError as e:
            logging.error(f"Не удалось декодировать JSON от воркера: {e}")
            return

        logging.info("Ожидание подтверждения от пользователя...")
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText(f"<b>Запрос на изменение проекта «{self._project_name}»</b>")
        msg_box.setInformativeText(
            f"Сервер запрашивает разрешение на создание или обновление "
            f"<b>{len(files)}</b> файлов. Разрешить операцию?"
        )
        msg_box.setWindowTitle("Подтверждение синхронизации")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        reply = msg_box.exec()

        if reply == QMessageBox.StandardButton.Yes:
            logging.info("Пользователь подтвердил обновление файлов.")
            stats = self._apply_updates(files)
            self._show_update_summary(stats)
        else:
            logging.warning("Пользователь отклонил обновление файлов.")

    def _apply_updates(self, files: List[Dict[str, str]]) -> UpdateStats:
        """Применяет изменения к файловой системе с проверками безопасности."""
        logging.info("Начинаю применение обновлений...")
        stats = UpdateStats(success=0, failed=0, skipped=0)
        root_dir_str = str(ROOT_DIR)
        for file_data in files:
            relative_path_str = file_data.get("path")
            content = file_data.get("content")
            if not relative_path_str or content is None:
                logging.warning(f"Пропущен файл с неполными данными: {file_data}")
                stats = stats._replace(skipped=stats.skipped + 1)
                continue
            try:
                target_path = Path(os.path.normpath(relative_path_str))
                if target_path.is_absolute():
                    logging.error(f"[БЕЗОПАСНОСТЬ] Отклонена попытка записи по абсолютному пути: '{target_path}'")
                    stats = stats._replace(failed=stats.failed + 1)
                    continue

                full_path = (ROOT_DIR / target_path).resolve()

                if not str(full_path).startswith(root_dir_str):
                    logging.error(f"[БЕЗОПАСНОСТЬ] Отклонена попытка выхода за пределы корневой директории: '{target_path}' -> '{full_path}'")
                    stats = stats._replace(failed=stats.failed + 1)
                    continue

                if self._gitignore_filter.is_ignored(full_path):
                    logging.warning(f"[БЕЗОПАСНОСТЬ] Отклонена попытка записи в игнорируемый путь: '{full_path}'")
                    stats = stats._replace(failed=stats.failed + 1)
                    continue

                action = "Обновление" if full_path.exists() else "Создание"
                logging.info(f"{action} файла: '{full_path}'")
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                stats = stats._replace(success=stats.success + 1)
            except Exception as e:
                logging.error(f"Не удалось обработать файл '{relative_path_str}': {e}", exc_info=True)
                stats = stats._replace(failed=stats.failed + 1)
        logging.info(f"Применение обновлений завершено. Успешно: {stats.success}, Ошибок: {stats.failed}, Пропущено: {stats.skipped}")
        return stats

    def _show_update_summary(self, stats: UpdateStats):
        """Показывает системное уведомление с итогами синхронизации."""
        if stats.failed > 0:
            title = "Синхронизация завершена с ошибками"
            message = (f"Успешно: {stats.success}, Ошибок: {stats.failed}.\nПодробности в логах.")
            icon = QSystemTrayIcon.MessageIcon.Warning
        else:
            title = "Синхронизация завершена"
            message = f"Успешно обновлено {stats.success} файлов."
            icon = QSystemTrayIcon.MessageIcon.Information
        self._tray_icon.showMessage(title, message, icon, 5000)


def main():
    app = LitSyncApp(sys.argv)
    sys.exit(app.run())


if __name__ == "__main__":
    main()