

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from supportflow.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[BaseCheckpointSaver]:
    """打开记忆存储，退出时关掉。

    配置了 `LANGGRAPH_PG_DSN` 就连 PostgreSQL：进程重启、网页刷新都还记得。
    没配置就退回内存版（能跑，但进程一停对话就没了），并打一条警告，

    """
    if not settings.LANGGRAPH_PG_DSN:
        logger.warning(
            "未配置 LANGGRAPH_PG_DSN，对话记忆只存在内存里，服务重启即丢失。"
        )
        yield InMemorySaver()
        return

    async with AsyncPostgresSaver.from_conn_string(settings.LANGGRAPH_PG_DSN) as saver:
        # setup 幂等，重复调用安全。
        await saver.setup()
        yield saver
