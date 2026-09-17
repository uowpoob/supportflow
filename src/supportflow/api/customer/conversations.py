"""客户对话会话接口。"""

from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(tags=["customer"])


@router.get("/conversations")
async def list_conversations(offset: int = 0, limit: int = 10):
    """我的对话会话列表（对应 `conversations` 表）。"""
    return result.success()
