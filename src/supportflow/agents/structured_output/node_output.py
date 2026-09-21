"""路由模型只识别需求、整理检索问题；具体节点由代码决定。"""

from pydantic import BaseModel, ConfigDict, Field

from supportflow.agents.graph.state import Intent


class UnderstandAndRouteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent = Field(description="结合完整对话识别本轮需求，分类不代表授权提交退款")
    knowledge_question: str | None = Field(
        default=None,
        description="知识咨询时，将本轮问题结合上下文改写成完整检索问题；其他意图为空",
    )
    product_model: str | None = Field(
        default=None,
        description="本轮咨询商品的明确型号，只从用户或工具结果获取，不猜测、不沿用其他商品型号",
    )
