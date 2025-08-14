from typing import Optional

import httpx


class Context7Exception(Exception):
    """Базовое исключение для ошибок клиента context7."""
    pass


class APIError(Context7Exception):
    """
    Возникает, когда API возвращает ошибку (не 2xx статус) или невалидные данные.
    """
    def __init__(
        self,
        message: str,
        *,
        request: Optional[httpx.Request] = None,
        response: Optional[httpx.Response] = None,
    ):
        self.request = request
        self.response = response
        status_part = f" (Status: {response.status_code})" if response else ""
        super().__init__(f"{message}{status_part}")


class RateLimitError(APIError):
    """Возникает при ошибке 429 (превышен лимит запросов)."""
    pass