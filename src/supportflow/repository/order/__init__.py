"""订单数据访问子包：对外只暴露查询函数，实现在 `queries.py`。

调用方是 `services/orders.py` —— 那是对外稳定的入口，HTTP 路由和 Agent Tool 都走它。
依赖方向只有一条：services → repository；这里不许 import services 里的任何东西。
"""

from supportflow.repository.order.queries import (
    get_order_any,
    get_order_for_user,
    get_order_with_items_for_user,
    list_all_orders,
    list_order_items,
    list_orders_for_user,
)

__all__ = [
    "get_order_any",
    "get_order_for_user",
    "get_order_with_items_for_user",
    "list_all_orders",
    "list_order_items",
    "list_orders_for_user",
]
