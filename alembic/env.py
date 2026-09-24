"""通过 asyncmy 运行迁移；凭据只来自环境变量或根目录 .env。"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from supportflow.core.database import DatabaseSettings
from supportflow.db.base import Base
import supportflow.models  # noqa: F401 -- 注册全部实体

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations(connection):
    context.configure(
        connection=connection, target_metadata=target_metadata,
        compare_type=True, compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(
        DatabaseSettings().database_url, poolclass=pool.NullPool,
        connect_args={"connect_timeout": 5, "read_timeout": 10},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=DatabaseSettings().database_url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run_migrations(config.attributes["connection"])
else:
    asyncio.run(run_online())
