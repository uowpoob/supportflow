import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supportflow.core.security import verify_password
from supportflow.models.entities import User
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