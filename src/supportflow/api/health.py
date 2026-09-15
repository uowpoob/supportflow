"""健康检查接口。"""

from fastapi import APIRouter

from supportflow.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """仅检查进程存活，不代表数据库或模型可用。"""
    return HealthResponse()
