"""Shared API response envelope.

All success responses use ``ApiResponse[T]`` so clients get a uniform
``{status, message, data}`` shape.
"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    status: Literal["success", "error"]
    message: str
    data: T | None = None
