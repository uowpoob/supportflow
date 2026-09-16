"""请求级依赖：把"认证态"翻译成"当前用户"。

身份**只能**来自 Cookie。请求参数、请求体、模型输出都不能决定你是谁 ——
这是防住"随便传个 user_id 就能看别人订单"这类越权的前提。
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.core.auth import SESSION_COOKIE_NAME
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.services.login import resolve_session


def _unauthorized() -> HTTPException:
    """每次新建异常对象，不要复用模块级实例（会累积 traceback）。"""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或会话已失效",
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """依赖：拿到当前登录用户，拿不到就 401。

    "没带 Cookie""凭证查不到""已过期""账号被停用"四种情况**返回完全一样的 401**，
    不告诉调用方是哪一种 —— 否则等于帮他确认某个凭证是否存在。
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await resolve_session(db, token) if token else None
    if user is None:
        raise _unauthorized()
    return user
