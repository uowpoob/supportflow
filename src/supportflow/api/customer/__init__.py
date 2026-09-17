"""客户接口域。

这里只做两件事：给整个域挂上 `/customer` 前缀和客户准入，再把子模块的路由拼起来。
准入挂在这一层，子模块的 handler 里就不用再写角色判断，也不会漏挂。
"""

from fastapi import APIRouter, Depends

from supportflow.api.auth.deps import require_customer
from supportflow.api.customer.conversations import router as conversations_router
from supportflow.api.customer.orders import router as orders_router
from supportflow.api.customer.refunds import router as refunds_router

router = APIRouter(prefix="/customer", dependencies=[Depends(require_customer)])

router.include_router(orders_router)
router.include_router(refunds_router)
router.include_router(conversations_router)
