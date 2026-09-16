from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Success(BaseModel, Generic[T]):
    code: str = "200"
    message: str = "ok"
    data: T


class success(Success[dict]):
    """兼容尚未声明具体响应数据类型的业务接口。"""
    data:dict= Field(default_factory=dict)

class Error(BaseModel):
    code:str = "400"
    message:str = "error"
    data:dict

