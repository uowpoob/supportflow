import asyncio
from datetime import datetime, timedelta
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from supportflow.core.security import generate_session_token, hash_session_token, verify_password
from supportflow.db.base import utc_now
from supportflow.models.entities import AuthSession, User
from supportflow.schemas.login import LoginRequest


async def authenticate_user(
    db: AsyncSession,
    request: LoginRequest,
) -> User | None:
    query = select(User).where(User.username == request.username)
    user = await db.scalar(query)

    if user is None:
        return None

    password_valid = await asyncio.to_thread(
        verify_password,
        request.password,
        user.password_hash,
    )

    if not password_valid or not user.is_active:
        return None

    return user


async def create_login_session(
    db: AsyncSession,
    user_id: int,
    ttl_seconds: int,
) -> tuple[str, datetime]:
    """提交会话后才返回原始凭证，避免数据库写入失败却下发 Cookie。"""
    # 顺手把已过期的会话记录删掉
    await db.execute(delete(AuthSession).where(AuthSession.expires_at <= utc_now()))
    token = generate_session_token()
    expires_at = utc_now() + timedelta(seconds=ttl_seconds)
    db.add(AuthSession(
        token_hash=hash_session_token(token),
        user_id=user_id,
        expires_at=expires_at,
    ))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return token, expires_at


async def resolve_session(
    db: AsyncSession,
    token: str,
) -> User | None:
    """用 Cookie 里的凭证原文找出当前用户；任一项不满足都返回 None。

    只比对 SHA-256 摘要：数据库里没有凭证原文，库被读走也换不回可用的 Cookie。
    """
    auth_session = await db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    if auth_session is None or auth_session.expires_at <= utc_now():
        return None

    user = await db.scalar(select(User).where(User.id == auth_session.user_id))
    if user is None or not user.is_active:
        return None

    return user


async def revoke_session(
    db: AsyncSession,
    token: str,
) -> bool:
    """撤销 Cookie 对应的那条会话记录，返回是否真的删掉了一行。

    只删这一条 —— 即"退出当前这个浏览器"，不是"退出所有设备"
    （后者要按 user_id 删，是另一个功能）。

    查不到也当成功、不抛错：调用方（登出接口）不该区分"这条凭证存在但已过期"
    与"这条凭证根本不存在"，否则它又变成一枚凭证探测器。
    """
    result = await db.execute(
        delete(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return bool(result.rowcount)
