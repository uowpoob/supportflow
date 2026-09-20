"""订单查询 Agent
"""

from langchain.agents import create_agent
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.llm import client
from supportflow.agents.prompt.system import ORDER_AGENT_SYSTEM_PROMPT
from supportflow.agents.tools.order_tools import build_order_tools



def build_order_agent(db: AsyncSession, user_id: int, *, checkpointer=None):

    return create_agent(
        model=client,
        tools=build_order_tools(db, user_id),
        system_prompt=ORDER_AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )



