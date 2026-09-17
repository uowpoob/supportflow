"""当前登录用户接口。

前端刷新页面后本地什么都不知道了，靠它向**服务端**确认"我是谁"，
而不是相信浏览器里存着的那份身份信息（那份用户随手就能改）。
"""

from fastapi import APIRouter, Depends

from supportflow.api.auth.deps import get_current_user
from supportflow.models.entities import User
from supportflow.schemas.login import LoginResponse
from supportflow.schemas.result import Success

router = APIRouter(tags=["me"])


@router.get("/me", response_model=Success[LoginResponse])
async def read_current_user(
    user: User = Depends(get_current_user),
) -> Success[LoginResponse]:
    """与 `POST /login` 返回同一份身份信息（id / username / role）。

    未登录、凭证无效、凭证过期、账号停用 —— 一律 401，且响应体完全相同。
    """
    return Success[LoginResponse](
        data=LoginResponse(id=user.id, username=user.username, role=user.role),
    )
