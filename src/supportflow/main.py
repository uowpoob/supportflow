"""SupportFlow HTTP entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from supportflow.agents.checkpointer import open_checkpointer
from supportflow.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """服务启动时打开对话记忆，全进程共用一份；退出时关掉。

    放在这里而不是每个请求各自开一个：连数据库是要花时间的，每个请求都连一遍
    既慢又费连接。挂到 `app.state` 上，路由通过 `Request` 就能拿到。
    """
    async with open_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        yield


app = FastAPI(
    title="SupportFlow",
    description="智能售后工单助手：逐步构建可评测的 Agent 服务。",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(api_router)
