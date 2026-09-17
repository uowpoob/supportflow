"""退款业务的异常类型。

单独成一个模块（而不是散在 `eligibility.py` 里），因为**每个子模块都要用它**：
资格判定、提交申请、审批复核都会抛。挂在任何一个业务模块里都会让其他模块
为了拿一个异常类去 import 那个模块的整条依赖链。
"""


class RefundError(Exception):
    """业务规则拒绝。路由层负责把它翻成 HTTP 响应。

    单独定义异常类型而不是直接抛 HTTPException，是为了让这一层不 import FastAPI ——
    以后 Agent Tool 调它时，不该被 HTTP 语义绑住。
    """

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
