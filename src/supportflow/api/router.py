"""汇总接口路由，由 main.py 统一注册。"""

from fastapi import APIRouter

from supportflow.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
