# gui.py
"""
Модуль для графического интерфейса пользователя (GUI) LitSync-Client.

Версия 2.0: Удален перехват closeEvent для обеспечения стандартного
поведения закрытия приложения.
"""
import logging
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QTabWidget, QPlainTextEdit
)

# Цветовая схема для статусов
STATUS_COLORS = {
    "connecting": "#e67e22",  # оранжевый
    "connected": "#2ecc71",   # зеленый
    "disconnected": "#f39c12", # желтый
    "error": "#e74c3c",       # красный
    "default": "#bdc3c7"      # серый
}


class QtLogHandler(logging.Handler, QObject):
    """
    Кастомный обработчик логов, который эмитирует сигнал для каждого сообщения.
    Это необходимо для безопасной передачи логов из любого потока в главный GUI-поток.
    """
    log_record = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        logging.Handler.__init__(self)
        QObject.__init__(self, parent)

    def emit(self, record: logging.LogRecord) -> None:
        """Форматирует и эмитирует запись лога как сигнал."""
        msg = self.format(record)
        self.log_record.emit(msg)


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    Отображает статус подключения и консоль логов.
    """
    reconnect_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("LitSync Client - Панель управления")
        self.setFixedSize(600, 400)
        self._init_ui()
        # Устанавливаем первоначальный статус
        self.update_status("Инициализация...", "default")

    def _init_ui(self) -> None:
        """Инициализирует все элементы интерфейса."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Создание вкладок
        tabs = QTabWidget()
        status_tab = QWidget()
        console_tab = QWidget()
        tabs.addTab(status_tab, "Статус")
        tabs.addTab(console_tab, "Консоль")
        main_layout.addWidget(tabs)

        # --- Вкладка "Статус" ---
        status_layout = QVBoxLayout(status_tab)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.setSpacing(20)

        self.status_label = QLabel("Инициализация...")
        font = self.status_label.font()
        font.setPointSize(16)
        font.setBold(True)
        self.status_label.setFont(font)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reconnect_button = QPushButton("Переподключиться")
        self.reconnect_button.setMinimumSize(150, 40)
        self.reconnect_button.clicked.connect(self.reconnect_requested.emit)
        self.reconnect_button.setEnabled(False) # Изначально выключена

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.reconnect_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- Вкладка "Консоль" ---
        console_layout = QVBoxLayout(console_tab)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #2b2b2b; color: #f2f2f2; font-family: Consolas, monaco, monospace;")
        console_layout.addWidget(self.log_console)

    def update_status(self, text: str, state: str) -> None:
        """
        Обновляет текстовый статус и цвет метки.
        Включает/выключает кнопку переподключения.

        Args:
            text: Текст для отображения.
            state: Ключ состояния ('connecting', 'connected', 'error', etc.).
        """
        color = STATUS_COLORS.get(state, STATUS_COLORS["default"])
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
        # Кнопка активна только в случае ошибки или явного отключения
        is_reconnectable = state in ("error", "disconnected")
        self.reconnect_button.setEnabled(is_reconnectable)

    def append_log(self, text: str) -> None:
        """Добавляет строку в консоль логов и прокручивает вниз."""
        self.log_console.appendPlainText(text)
        self.log_console.verticalScrollBar().setValue(
            self.log_console.verticalScrollBar().maximum()
        )

    # Метод closeEvent был удален, чтобы окно закрывалось стандартным образом,
    # вызывая завершение работы QApplication.