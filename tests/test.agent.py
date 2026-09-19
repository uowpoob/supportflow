"""跑一遍订单 Agent，看每一轮它到底干了什么。

在 PyCharm 里直接右键 Run 这个文件就行，不需要开后端服务（脚本直接连数据库）。

需要的是：MySQL 在跑。

用的是 stream_mode="updates"：每跑完一个节点吐一次，只给"这一步改了什么"。
正常一轮是 model → tools → model 三次；如果只看到 model 一次，
说明模型压根没调工具（去看 prompt/system.py 里的范围句）。
"""

import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from supportflow.agent.order_agent import build_order_agent
from supportflow.db.session import SessionLocal

USER_ID = 4
CONFIG = {"configurable": {"thread_id": "demo-1"}}

QUESTIONS = [
    "我都有啥订单",
    "我买的充电宝还能退款吗",
    "不是"
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
    # 1. 开一个数据库会话
    async with SessionLocal() as db:
        # 2. 造图：把「谁能看哪些数据」钉在这一步
        graph = build_order_agent(db, USER_ID, checkpointer=InMemorySaver())

        # 3. 一句一句问
        for question in QUESTIONS:
            print(f"\n{'=' * 48}\n我 > {question}")

            # 注意：updates / values 模式一次只吐一个东西，所以是一个变量。
            # （messages 模式才是两个：chunk, info）
            async for update in graph.astream(
                    {"messages": [{"role": "user", "content": question}]},
                    CONFIG,
                    stream_mode="updates",
            ):
                show(update)


if __name__ == "__main__":
    asyncio.run(main())
