"""退出登录：撤销服务端会话 + 让浏览器丢掉 Cookie。
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.core.auth import SESSION_COOKIE_NAME, auth_settings
from supportflow.db.session import get_db
from supportflow.schemas.result import Success
from supportflow.services.login import revoke_session

router = APIRouter(tags=["logout"])


@router.post("/logout", response_model=Success[dict])
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Success[dict]:
    """登出。
    1. 登出必须幂等：没登录、凭证已过期、凭证是伪造的 —— 一律返回 200。
       用户点"退出"这个动作本身不该失败，否则前端会卡在"退了但状态没清"。
    2. 若在这里也做鉴权，401 与 200 的差别就等于告诉调用方
       "这个凭证是真的"，又变成一个探测器。
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session(db, token)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=auth_settings.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return Success[dict](data={})
