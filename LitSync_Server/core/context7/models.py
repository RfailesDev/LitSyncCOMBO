from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Определяем тип для состояния документа, как в TypeScript
DocumentState = Literal["initial", "finalized", "error", "delete"]


class SearchResult(BaseModel):
    """
    Представляет один результат поиска из Context7 API.
    Использует псевдонимы для маппинга полей snake_case на camelCase JSON.
    """
    id: str
    title: str
    description: str
    branch: str
    last_update_date: str = Field(alias="lastUpdateDate")
    state: DocumentState
    total_tokens: int = Field(alias="totalTokens")
    total_snippets: int = Field(alias="totalSnippets")
    total_pages: int = Field(alias="totalPages")
    stars: Optional[int] = None
    # ИСПРАВЛЕНИЕ: Изменен тип с int на float для поддержки дробных значений.
    trust_score: Optional[float] = Field(alias="trustScore", default=None)
    versions: Optional[List[str]] = None

    class Config:
        # Pydantic v2 использует `populate_by_name` для работы с псевдонимами.
        populate_by_name = True


class SearchResponse(BaseModel):
    """
    Представляет полный ответ на поисковый запрос.
    """
    results: List[SearchResult]
    error: Optional[str] = None