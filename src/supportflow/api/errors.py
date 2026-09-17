"""业务异常 → HTTP 响应的翻译层。

业务层（`services/`）刻意不 import FastAPI —— 以后 Agent Tool 调同一批函数时，
不该被 HTTP 语义绑住。所以"规则拒绝"在那一层是 `RefundError`，
到这里才被翻成 404 / 409。

为什么不挂全局异常处理器？因为那样"这个接口会返回哪些错误"会变成隐式的，
得去翻 `main.py` 才知道。路由里显式写一句 try/except，读代码的人一眼就看到
"这条规则拒绝会变成 409"。
"""

from fastapi import HTTPException

from supportflow.services.refunds import RefundError


def to_http_error(error: RefundError) -> HTTPException:
    """把业务异常翻成 HTTP 异常，**状态码由业务层决定**。

    让业务层决定状态码是要紧的：`order_not_found` 必须和订单详情一样是 404
    （归到 409 就等于承认"这个订单号存在，只是现在不能退"），
    而"已过 14 天"该是 409 —— 请求本身没毛病，是当前状态不允许。
    """
    return HTTPException(status_code=error.status_code, detail=error.message)
