"""售后总图节点；意图路由已实现，其余节点后续逐个实现。

LangGraph 将完整 State 传给节点，通过 Runtime 注入本次 Context：
    context = runtime.context
    user_id = context.user_id
    order = state["order"]
返回 SupportStateUpdate，只更新需要变动的顶层字段，不原地修改 State。

未实现节点明确抛出 NotImplementedError，避免把空实现误当成业务成功。
仅在执行意图路由时加载模型客户端；导入和画图不初始化模型或连接数据库。
"""

import json

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState, SupportStateUpdate, initial_state
from supportflow.agents.prompt.routing import ROUTING_SYSTEM_PROMPT
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput


def _get_router_model():
    # 延迟导入：编译总图、画图和离线测试无需模型密钥。
    from supportflow.agents.llm import client

    return client.with_structured_output(UnderstandAndRouteOutput)


async def understand_and_route(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """结合历史和办理进度识别意图，返回 State 更新，由总图条件边分流。

    这一阶段只判断意图、处理目的和出口。订单确认、换单清理、退款原因提取
    以及取消操作，留给后续业务节点处理，不从分类结果伪造这些业务事实。
    """
    context = runtime.context
    if not state.get("messages"):
        raise ValueError("意图路由需要非空的 messages")

    defaults = initial_state()
    current = {**defaults, **state}
    progress = {key: current[key] for key in (
        "current_intent", "order", "refund", "knowledge",
    )}
    router_model = _get_router_model()
    result = await router_model.ainvoke([
        SystemMessage(content=ROUTING_SYSTEM_PROMPT),
        SystemMessage(content="当前办理进度：\n" + json.dumps(progress, ensure_ascii=False)),
        *state["messages"],
    ])
    # Pydantic schema 对应的 with_structured_output 返回模型实例，用属性读取。
    intent = result.intent
    next_node = result.next_node

    # 模型负责语义判断，代码约束合法的业务入口。
    if intent == "unknown":
        next_node = "clarify"
    elif next_node != "clarify":
        if intent == "order_query":
            next_node = "order_agent"
        elif intent == "refund_query":
            next_node = "refund_agent"
        elif intent == "refund_request":
            has_order = current["refund"]["order_no"] or current["order"]["selected_order_no"]
            # 候选订单还未确认时不能跳过定位；已有订单时仍允许用户换单去订单节点。
            if not has_order or next_node == "order_agent":
                next_node = "order_agent"
            else:
                next_node = "refund_agent"
        elif next_node != "order_agent":
            next_node = "prepare_knowledge"

    # 支持新会话只传 messages；已有 checkpoint 字段不重置。
    updates: SupportStateUpdate = {
        key: value for key, value in defaults.items()
        if key not in state and key != "messages"
    }
    updates.update(current_intent=intent, next_node=next_node)
    if next_node == "order_agent":
        purpose = (
            "refund" if intent == "refund_request"
            else "knowledge" if intent in ("product_support", "policy_question")
            else "order_query"
        )
        updates["order"] = {**current["order"], "purpose": purpose}
    if intent in ("product_support", "policy_question"):
        updates["knowledge"] = {
            **current["knowledge"],
            "topic": "product_support" if intent == "product_support" else "policy",
        }
        updates["retrieved_documents"] = []
    return updates


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
