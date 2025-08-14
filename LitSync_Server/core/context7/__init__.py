"""
A simple, modern client for the Context7 API.
This package contains the client, data models, and custom exceptions
for interacting with the Context7 service.
"""
from .client import Context7Client
from .exceptions import APIError, Context7Exception, RateLimitError
from .models import DocumentState, SearchResponse, SearchResult

__all__ = [
    "Context7Client",
    "SearchResponse",
    "SearchResult",
    "DocumentState",
    "Context7Exception",
    "APIError",
    "RateLimitError",
]