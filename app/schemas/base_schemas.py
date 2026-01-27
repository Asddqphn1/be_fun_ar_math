from typing import Generic, Optional, TypeVar

from pydantic import BaseModel


T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    success: str
    message: str
    data: Optional[T] = None