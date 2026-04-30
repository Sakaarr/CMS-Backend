from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def success_response(data: Any = None, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data}


def paginated_response(
    data: list,
    total: int,
    page: int,
    page_size: int,
) -> dict:
    return {
        "success": True,
        "message": "OK",
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size),  # ceiling division
    }