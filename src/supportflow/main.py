"""SupportFlow HTTP entry point."""

from fastapi import FastAPI

from supportflow.api.router import api_router

app = FastAPI(
    title="SupportFlow",
    description="智能售后工单助手：逐步构建可评测的 Agent 服务。",
    version="0.1.0",
)


app.include_router(api_router)
