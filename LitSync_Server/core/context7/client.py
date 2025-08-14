import logging
from typing import Dict, Optional

import httpx
from pydantic import ValidationError

from .exceptions import APIError, RateLimitError
from .models import SearchResponse

logger = logging.getLogger(__name__)

# --- КОНСТАНТЫ ---
CONTEXT7_API_BASE_URL = "https://context7.com/api/v1"
DEFAULT_TYPE = "txt"
DEFAULT_TIMEOUT = 15.0


class Context7Client:
    """
    Промышленный, отказоустойчивый синхронный клиент для взаимодействия с Context7 API.
    """

    def __init__(
        self,
        *,
        base_url: str = CONTEXT7_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        httpx_client: Optional[httpx.Client] = None,
    ):
        """
        Инициализирует клиент.

        Args:
            base_url: Базовый URL для API.
            timeout: Таймаут запроса по умолчанию в секундах.
            httpx_client: Опциональный существующий экземпляр httpx.Client.
                          Если не предоставлен, будет создан новый.
        """
        if httpx_client:
            self._client = httpx_client
            self._managed_client = False
        else:
            self._client = httpx.Client(base_url=base_url, timeout=timeout)
            self._managed_client = True

        self._headers = {"X-Context7-Source": "context7-python-client"}

    def search(self, query: str) -> SearchResponse:
        """
        Ищет библиотеки, соответствующие запросу.

        Raises:
            RateLimitError: При ошибке 429 (превышен лимит запросов).
            APIError: Для других ошибок, связанных с API.
        """
        response: Optional[httpx.Response] = None
        try:
            response = self._client.get(
                "/search", params={"query": query}, headers=self._headers
            )
            response.raise_for_status()
            return SearchResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    "Rate limited due to too many requests.",
                    request=e.request,
                    response=e.response,
                ) from e
            raise APIError(
                f"API request failed with status {e.response.status_code}",
                request=e.request,
                response=e.response,
            ) from e
        except (ValidationError, TypeError) as e:
            logger.error(f"Ошибка валидации ответа от Context7 API: {e}", exc_info=True)
            raise APIError(
                f"Failed to parse API response: {e}",
                request=response.request if response else None,
                response=response,
            ) from e

    def fetch_documentation(
        self,
        library_id: str,
        *,
        tokens: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> Optional[str]:
        """
        Получает текст документации для конкретной библиотеки.

        Returns:
            Текст документации в виде строки или None, если контент недоступен или не найден.
        """
        if library_id.startswith("/"):
            library_id = library_id.lstrip("/")

        params: Dict[str, str | int] = {"type": DEFAULT_TYPE}
        if tokens:
            params["tokens"] = tokens
        if topic:
            params["topic"] = topic

        try:
            response = self._client.get(f"/{library_id}", params=params, headers=self._headers)
            if response.status_code == 404:
                logger.warning(f"Документация для library_id '{library_id}' не найдена (404).")
                return None
            response.raise_for_status()

            text = response.text
            if not text or text.strip() in ("No content available", "No context data available"):
                logger.info(f"Для library_id '{library_id}' получен пустой ответ.")
                return None
            return text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    "Rate limited due to too many requests.",
                    request=e.request,
                    response=e.response,
                ) from e
            raise APIError(
                f"API request failed with status {e.response.status_code}",
                request=e.request,
                response=e.response,
            ) from e

    def close(self) -> None:
        """Закрывает внутренний httpx клиент, если он был создан этим экземпляром."""
        if self._managed_client and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> "Context7Client":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()