"""意图路由的模型输出；与保存对话历史的 State 分开。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from supportflow.agents.graph.state import Intent


class UnderstandAndRouteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent = Field(description="结合完整对话和办理进度识别本轮用户意图")
    next_node: Literal[
        "order_agent", "refund_agent", "prepare_knowledge", "clarify",
    ] = Field(description=(
        "建议交给哪个节点；意图是用户要做什么，节点是当前由谁处理。"
        "退款尚未确定订单时先交 order_agent；知识咨询需要从购买记录找商品时"
        "也可交 order_agent。无法确定时交 clarify。"
    ))
