"""跑一遍统一售后 Agent，看每一轮它到底干了什么。

在 PyCharm 里直接右键 Run 这个文件就行，不需要开后端服务（脚本直接连数据库）。
"""

import asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from supportflow.agents.graph.builder import build_support_graph
from supportflow.agents.graph.context import SupportContext
from supportflow.core.config import settings
from supportflow.db.session import SessionLocal

USER_ID = 4
# 提交退款时，替换为 MySQL 中属于 USER_ID 的真实会话 ID。
CONVERSATION_ID = "test-1"
THREAD_ID = CONVERSATION_ID
CONFIG = {"configurable": {"thread_id": THREAD_ID}}
QUESTIONS = [
    "华为",
    "我想申请售后"

]


def show(update: dict) -> None:
    """把一个 update 压成人看得懂的样子。

    update 长这样：{"model": {"messages": [...]}} —— 外面那个键是节点名。
    想看原始对象，把这里整段换成 `print(update)` 就行。
    """
    for node, data in update.items():
        print(f"\n--- 节点 {node} ---")

        for message in data.get("messages", []):
            calls = getattr(message, "tool_calls", None)
            if calls:
                for call in calls:
                    print(f"  → 调用工具 {call['name']}({call['args']})")
            elif message.type == "tool":
                text = str(message.content).replace("\n", " ")
                print(f"  ← 工具返回 {text[:160]}{'…' if len(text) > 160 else ''}")
            elif message.content:
                print(f"  模型说：{message.content}")


async def main() -> None:
    # 1. 连上 Postgres。from_conn_string 要用 async with 包起来，
    #    出了这个块连接自动关掉，不会泄漏连接。
    async with AsyncPostgresSaver.from_conn_string(settings.LANGGRAPH_PG_DSN) as saver:
        # 2. setup() 负责那 4 张记忆表：没有就建，版本旧就升级。
        #    表已经在了的时候它就是空转，重复调用无害。
        await saver.setup()
        # 需要清理测试历史时再手动开启，平时保留多轮记忆。
        # await saver.adelete_thread(THREAD_ID)

        # 3. 开一个业务库（MySQL）的会话
        async with SessionLocal() as db:
            # 4. 造图：「谁能看哪些数据」钉在这一步，「记忆存哪」交给 saver
            graph = build_support_graph(checkpointer=saver)
            context = SupportContext(USER_ID, CONVERSATION_ID, db)

            # 5. 一句一句问
            for question in QUESTIONS:
                print(f"\n{'=' * 48}\n我 > {question}")

                # 注意：updates / values 模式一次只吐一个东西，所以是一个变量。
                # （messages 模式才是两个：chunk, info）
                async for update in graph.astream(
                        {"messages": [{"role": "user", "content": question}]},
                        CONFIG,
                        context=context,
                        stream_mode="updates",
                ):
                    show(update)


if __name__ == "__main__":
    asyncio.run(main(),loop_factory=asyncio.SelectorEventLoop)
