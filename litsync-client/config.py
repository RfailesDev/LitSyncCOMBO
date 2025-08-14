# config.py
"""
Конфигурационный файл для LitSync-Client.
"""
import sys
from pathlib import Path

# --- Сетевые настройки ---
# ИЗМЕНЕНО: URL'ы разделены для поддержки прокси
# 1. Прямое безопасное соединение (по умолчанию)
HTTPS_URL_DIRECT: str = "https://litsync.darkserver-eu.ru:443"
# 2. HTTP соединение для использования с прокси
HTTP_URL_VIA_PROXY: str = "http://darkserver-eu.ru:6032"
# 3. Адрес локального SOCKS5 прокси для проверки
SOCKS_PROXY_URL: str = "socks5://127.0.0.1:10808"
# 4. URL для проверки работоспособности прокси
PROXY_TEST_URL: str = "https://google.com"
PROXY_TEST_TIMEOUT_SECONDS: int = 5

CLIENT_NAMESPACE: str = "/client"

# --- Настройки переподключения ---
RECONNECT_DELAY_SECONDS: int = 15
RECONNECT_DELAY_MAX_SECONDS: int = 60
CONNECTION_TIMEOUT_SECONDS: int = 10

# --- Настройки приложения ---
APP_NAME: str = "LitSync-Client"
APP_VERSION: str = "4.0.0" # Версия обновлена для отражения изменений

# --- Настройки фильтрации файлов ---
# Максимальный размер файла в байтах, который будет считываться.
# Предотвращает чтение больших бинарных файлов (видео, архивы, образы).
# 10 МБ = 10 * 1024 * 1024 = 10485760 байт
MAX_FILE_SIZE_BYTES: int = 10_485_760

# Размер фрагмента в байтах для определения, является ли файл бинарным.
# Чтение небольшого фрагмента намного быстрее, чем чтение всего файла.
BINARY_DETECTION_CHUNK_SIZE: int = 4096

# Набор расширений файлов, которые всегда считаются бинарными и пропускаются.
# Использование set() обеспечивает очень быструю проверку (O(1)).
BINARY_FILE_EXTENSIONS: set[str] = {
    # Исполняемые файлы и библиотеки
    ".exe", ".dll", ".so", ".o", ".a", ".lib", ".dylib",
    # Архивы
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    # Изображения
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".ico",
    # Аудио и видео
    ".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mkv", ".avi", ".mov", ".webm",
    # Документы
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
    # Шрифты
    ".ttf", ".otf", ".woff", ".woff2",
    # Базы данных и скомпилированные форматы
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo",
}


# --- КОРНЕВАЯ ДИРЕКТОРИЯ ПРОЕКТА ---
# Определяем корневую директорию относительно расположения этого файла.
# Это гарантирует, что приложение всегда будет работать с собственной папкой,
# независимо от того, откуда оно было запущено. Это критически важно для
# безопасности и предсказуемости поведения.
#
# Path(__file__) -> /path/to/litsync-client/config.py
# .parent -> /path/to/litsync-client/
# .resolve() -> /absolute/path/to/litsync-client/
#
# Проверяем, не запущено ли приложение через PyInstaller (в виде одного файла)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Если запущено как .exe, ROOT_DIR - это директория, где лежит .exe
    ROOT_DIR: Path = Path(sys.executable).parent.resolve()
else:
    # Если запущено как .py скрипт
    ROOT_DIR: Path = Path(__file__).parent.resolve()

# Директории, которые нужно исключить при подсчете файлов для идентификатора клиента.
# Этот список работает в дополнение к .gitignore как дополнительный уровень защиты.
EXCLUDED_DIRS = {".git", ".idea", "venv", "__pycache__"}