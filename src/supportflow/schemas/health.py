"""健康检查响应结构。"""

from typing import Literal

from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "supportflow"
