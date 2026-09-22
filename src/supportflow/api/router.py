"""汇总接口路由，由 main.py 统一注册。"""

from fastapi import APIRouter

from supportflow.api.admin import router as admin_router
from supportflow.api.auth.login import router as login_router
from supportflow.api.auth.logout import router as logout_router
from supportflow.api.auth.me import router as me_router
from supportflow.api.customer import router as customer_router
from supportflow.api.health import router as health_router


api_router = APIRouter()

api_router.include_router(admin_router)
api_router.include_router(login_router)
api_router.include_router(logout_router)
api_router.include_router(me_router)
api_router.include_router(customer_router)
api_router.include_router(health_router)

