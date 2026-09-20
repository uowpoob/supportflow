
from sqlalchemy.ext.asyncio import AsyncSession
from langchain.agents import create_agent
from supportflow.agents.llm import client
from supportflow.agents.prompt.system import  REFUND_AGENT_SYSTEM_PROMPT
from supportflow.agents.tools.refund_tools import build_refund_tools

def build_refund_agent(db: AsyncSession,user_id: int, *, checkpointer=None) :


    return create_agent(
        model=client,
        system_prompt=REFUND_AGENT_SYSTEM_PROMPT,
        checkpointer = checkpointer,
        tools=build_refund_tools(db, user_id)
        )