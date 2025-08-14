# config.py
"""
Централизованная конфигурация приложения.
Загружает настройки из переменных окружения с безопасными значениями по умолчанию.
"""
import os

# --- Сетевые настройки ---
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", 6032))

# --- Публичный базовый URL (для генерации upload-ссылок) ---
# Должен указывать на публичный HTTPS-домен сервера.
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "https://litsync.darkserver-eu.ru:443")
UPLOAD_PATH_PREFIX: str = os.getenv("UPLOAD_PATH_PREFIX", "/v2/upload")

# --- Безопасность ---
ALLOWED_ORIGIN: str = os.getenv("ALLOWED_ORIGIN", "*")
SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())

# --- Таймауты ожидания клиента ---
DEFAULT_CLIENT_TIMEOUT_SECONDS: int = int(os.getenv("DEFAULT_CLIENT_TIMEOUT_SECONDS", 60))

# --- Настройки Heartbeat ---
# Этот файл возвращен к исходному состоянию. Кастомные настройки heartbeat не нужны.


# --- Отладка ---
# Если переменная установлена (в любое непустое значение), функция будет активна
TEST_SAVE_ENABLED: bool = bool(os.getenv("TEST_SAVE_ENABLED", False))
# Путь для сохранения отладочных файлов
TEST_SAVE_PATH: str = os.getenv("TEST_SAVE_PATH", "_debug_requests")