"""对话记忆存在哪。

Agent 每轮对话都要把消息存下来，下次同一个会话接着聊。这份存储由**整个服务共用一份**：
服务启动时打开一次，之后所有请求都复用它 —— 不是每个请求都去新建一个连接。

业务数据在 MySQL（那边只管"这个会话属于谁"），对话内容在 PostgreSQL，
两边靠 thread_id 关联，thread_id 就是 `conversations` 表的主键。
"""

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
    免得把"内存记忆"误当成"持久化已经做好了"。
    """
    if not settings.LANGGRAPH_PG_DSN:
        logger.warning(
            "未配置 LANGGRAPH_PG_DSN，对话记忆只存在内存里，服务重启即丢失。"
        )
        yield InMemorySaver()
        return

    async with AsyncPostgresSaver.from_conn_string(settings.LANGGRAPH_PG_DSN) as saver:
        # 建表与升级表结构；表已经在了就是空转，重复调用安全。
        await saver.setup()
        yield saver
