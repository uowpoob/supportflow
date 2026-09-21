"""每次执行由服务端提供的身份和数据库资源，不写入 checkpoint。"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SupportContext:
    """节点通过 runtime.context 获取，而不是从消息中提取身份。

    调用方负责用户认证、会话归属校验，并让 thread_id 与 conversation_id
    一致。每次执行重新提供 Context；db 在整个调用/流式迭代期间必须保持打开，
    结束后由调用方关闭，不跨请求复用同一个 AsyncSession。
    """

    user_id: int
    conversation_id: str
    db: AsyncSession = field(repr=False, compare=False)
