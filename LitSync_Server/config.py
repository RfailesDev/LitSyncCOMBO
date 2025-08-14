# config.py
"""
Централизованная конфигурация приложения.
Загружает настройки из переменных окружения с безопасными значениями по умолчанию.
"""
import os

# --- Сетевые настройки ---
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", 6032))

# --- Безопасность ---
ALLOWED_ORIGIN: str = os.getenv("ALLOWED_ORIGIN", "*")
SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())

# --- Настройки Heartbeat ---
# Этот файл возвращен к исходному состоянию. Кастомные настройки heartbeat не нужны.


# --- Отладка ---
# Если переменная установлена (в любое непустое значение), функция будет активна
TEST_SAVE_ENABLED: bool = bool(os.getenv("TEST_SAVE_ENABLED", False))
# Путь для сохранения отладочных файлов
TEST_SAVE_PATH: str = os.getenv("TEST_SAVE_PATH", "_debug_requests")