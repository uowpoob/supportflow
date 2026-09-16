"""进程存活检查，不依赖登录、数据库或模型服务。"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "supportflow"}
