"""管理员接口域。

这里只做两件事：给整个域挂上 `/admin` 前缀和管理员准入，再把子模块的路由拼起来。
准入挂在这一层，子模块的 handler 里就不用再写角色判断，也不会漏挂。
"""

from fastapi import APIRouter, Depends

from supportflow.api.admin.orders import router as orders_router
from supportflow.api.admin.refunds import router as refunds_router
from supportflow.api.auth.deps import require_admin

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

router.include_router(orders_router)
router.include_router(refunds_router)
