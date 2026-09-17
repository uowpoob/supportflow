"""退出登录：撤销服务端会话 + 让浏览器丢掉 Cookie。

**为什么必须由后端来做**：登录时的 Cookie 带 `httponly=True`，前端 JS 读不到、
也删不掉它（这正是防 XSS 窃取的价值）。所以"删除"只能由后端再发一次
`Set-Cookie` 把值清空来完成，前端自己办不到。

真实退出要**同时**做两件事，缺一不可：

1. 服务端删掉 `auth_sessions` 里那条记录 —— 这一步才是真正的撤销。
   万一凭证之前被人截留过，只清浏览器那一份毫无用处。
2. 下发一个过期的 `Set-Cookie` —— 让浏览器丢掉手上那份凭证。

只做第 1 步：浏览器仍携带旧 Cookie，但服务端会话已撤销，`/me` 会返回 401。
只做第 2 步：库里会话越积越多，且被截留的凭证依然能用。
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
    """登出。**故意不挂 `get_current_user`**，理由有两条：

    1. 登出必须幂等：没登录、凭证已过期、凭证是伪造的 —— 一律返回 200。
       用户点"退出"这个动作本身不该失败，否则前端会卡在"退了但状态没清"。
    2. 若在这里也做鉴权，401 与 200 的差别就等于告诉调用方
       "这个凭证是真的"，又变成一个探测器。

    代价：接口本身不做身份校验是安全的 —— 它只会删掉**请求者自己出示的那个凭证**，
    没有凭证就什么都不删，不涉及任何越权。
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
