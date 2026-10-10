"""一键生成小米演示数据；--refresh 在单个事务内恢复完整演示基线。"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.db.seed import seed_orders, seed_refunds, seed_users
from supportflow.db.session import SessionLocal, engine
from supportflow.models import Order, RefundApproval, RefundRecord, RefundRequest


async def clear_demo_refunds(session: AsyncSession) -> None:
    """只重置声明的演示订单的退款链路；保留账号、登录会话和聊天会话。"""
    order_ids = list(await session.scalars(select(Order.id).where(
        Order.order_no.in_([spec.order_no for spec in seed_orders.DEMO_ORDERS])
    )))
    request_ids = list(await session.scalars(select(RefundRequest.id).where(
        RefundRequest.order_id.in_(order_ids)
    )))
    if request_ids:
        for model in (RefundRecord, RefundApproval):
            await session.execute(delete(model).where(model.refund_request_id.in_(request_ids)))
        await session.execute(delete(RefundRequest).where(RefundRequest.id.in_(request_ids)))
    await session.flush()


async def seed(session: AsyncSession, now: datetime, refresh: bool = False) -> dict:
    """事务由调用方负责，异常时订单与退款一起回滚。"""
    seed_orders._validate()
    seed_refunds._validate()
    users = await seed_users.seed(session)
    if refresh:
        await clear_demo_refunds(session)
    orders = await seed_orders.seed(session, now, refresh)
    refunds = await seed_refunds.seed(session, now)
    return {"users": users, "orders": orders, "refunds": refunds}


async def main(refresh: bool = False) -> None:
    try:
        async with SessionLocal() as session, session.begin():
            result = await seed(session, utc_now(), refresh)
        for username, role, password in result["users"]:
            print(f"username={username} role={role} password={password}")
        created, refreshed, skipped = result["orders"]
        requests, skipped_requests = result["refunds"]
        print(f"Orders: created {len(created)}, refreshed {len(refreshed)}, skipped {len(skipped)}")
        print(f"Refund requests: created {len(requests)}, skipped {len(skipped_requests)}")
        print("Customers:", dict(Counter(spec.username for spec in seed_orders.DEMO_ORDERS)))
        print("Refund states:", dict(Counter(spec.status.value for spec in seed_refunds.DEMO_REFUNDS)))
        print("Execution states:", dict(Counter(spec.record.status.value
              for spec in seed_refunds.DEMO_REFUNDS if spec.record)))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="同步恢复演示订单、明细和退款基线")
    asyncio.run(main(refresh=parser.parse_args().refresh))
