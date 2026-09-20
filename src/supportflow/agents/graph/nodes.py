"""总图节点接口，当前只定义职责和输入输出，后续逐个实现。

LangGraph 将完整 State 传给节点，通过 Runtime 注入本次 Context：
    context = runtime.context
    user_id = context.user_id
    order = state["order"]
返回 SupportStateUpdate，只更新需要变动的顶层字段，不原地修改 State。

占位节点明确抛出 NotImplementedError，避免把空实现误当成业务成功。
本模块不初始化模型、不连接数据库，也不新增 Knowledge Agent。
"""

from langgraph.runtime import Runtime

from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState, SupportStateUpdate


async def understand_and_route(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """结合新消息、历史和办理进度，更新意图与用户补充的信息。

    “对”“不喜欢”等短回复应结合上一轮问题理解；咨询政策时保留退款进度，
    换订单或取消时清理相应旧状态。每轮重新设置 next_node，不能沿用旧路由。
    出口：order_agent / refund_agent / prepare_knowledge / clarify / end。
    """
    context = runtime.context
    raise NotImplementedError("待实现：理解输入与意图路由")


async def order_agent(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """包装现有 Order Agent，查询当前用户订单，更新候选和确认结果。

    用户尚未确认：追问并设置 next_node='end'，等待下一轮。
    已确认且 purpose='refund'：同步退款订单，设置 next_node='refund_agent'。
    已确认且 purpose='knowledge'：同步咨询商品，设置 next_node='prepare_knowledge'。
    普通订单查询完成：设置 next_node='end'。不要仅因查到订单就视为已确认。
    子 Agent 的消息转交必须保留工具调用与结果的完整配对。
    """
    context = runtime.context
    raise NotImplementedError("待实现：订单 Agent 包装节点")


async def refund_agent(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """包装现有 Refund Agent，处理资格、原因、提交以及进度查询。

    申请缺订单时由前置路由送去定位订单；缺原因时追问并结束本轮。
    明确要求提交且信息齐全才调用业务工具，资格和幂等性由业务服务复核。
    request_key 来自工具结果；业务拒绝应转为可解释的回复，不能伪造成功。
    返回 messages 和退款子状态；无论回复还是追问，本节点后均结束本轮。
    """
    context = runtime.context
    raise NotImplementedError("待实现：退款 Agent 包装节点")


async def prepare_knowledge(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """补全检索问题与主题，检查必要的商品信息，并清空旧检索证据。

    一般政策问题不强制要求型号。具体产品咨询缺少必要信息时，保留待补全的
    knowledge 状态，设置 next_node='clarify'；齐全则设置 'retrieve_knowledge'。
    此节点不覆盖退款进度，也不把用户故障描述直接当作退款意图。
    """
    context = runtime.context
    raise NotImplementedError("待实现：准备知识检索输入")


async def retrieve_knowledge(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """调用检索服务，返回带文档/片段标识、标题、来源和正文的证据。

    按问题、主题和必要的商品型号检索；无结果必须返回 retrieved_documents=[]。
    检索结果整体替换，本节点不生成用户回答。检索服务在后续知识库阶段接入。
    """
    context = runtime.context
    raise NotImplementedError("待实现：文档检索节点")


async def answer_knowledge(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """普通节点调用模型，根据本轮证据回答并附来源，无需新建 Agent。

    先检查证据对问题和型号是否适用；无证据或证据不足时说明限制或追问，
    不编造条款及操作步骤。返回新增 messages，保持退款状态不变。
    """
    context = runtime.context
    raise NotImplementedError("待实现：根据文档回答")


async def clarify(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """按上下文询问当前缺失的信息，返回追问消息，保留已收集的信息。

    可以澄清用户意图或询问商品型号等。回复后结束本轮，下一轮再从路由进入。
    """
    context = runtime.context
    raise NotImplementedError("待实现：澄清与追问")
