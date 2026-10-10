"""创建本地模拟账号：python -m supportflow.db.seed.seed_users。"""

import asyncio
import secrets

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.session import SessionLocal, engine
from supportflow.models import User
from supportflow.models.enums import UserRole


DEMO_USERS = (
    ("admin", UserRole.ADMIN),
    ("customer1", UserRole.CUSTOMER),
    ("customer2", UserRole.CUSTOMER),
)


async def seed(session: AsyncSession) -> list[tuple[str, str, str]]:
    """只创建缺少的演示账号，已有账号的密码保持不变。"""
    created = []
    for username, role in DEMO_USERS:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing is not None:
            if existing.role is not role or not existing.is_active:
                raise ValueError(f"演示账号 {username} 的角色或启用状态不正确")
            continue
        password = secrets.token_urlsafe(16)
        password_hash = await asyncio.to_thread(
            bcrypt.hashpw, password.encode("utf-8"), bcrypt.gensalt(rounds=12)
        )
        if not await asyncio.to_thread(bcrypt.checkpw, password.encode("utf-8"), password_hash):
            raise RuntimeError("Password hash verification failed")
        session.add(User(username=username, password_hash=password_hash.decode("utf-8"),
                         role=role, is_active=True))
        created.append((username, role.value, password))
    await session.flush()
    return created


async def main() -> None:
    created = []
    try:
        async with SessionLocal() as session:
            # 三个账号一起提交；中途失败时事务回滚。
            async with session.begin():
                created = await seed(session)

        # 仅在提交成功后显示新账号密码，供本地演示登录使用。
        print(f"Created {len(created)} demo account(s).")
        for username, role, password in created:
            print(f"username={username} role={role} password={password}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
