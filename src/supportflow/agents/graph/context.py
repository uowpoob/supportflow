"""服务端为每次图执行提供的身份信息，不作为对话状态保存。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SupportContext:
    """由登录态和已校验归属的会话创建，不接受模型或消息正文指定。

    conversation_id 应与 config.configurable.thread_id 一致；后续路由层
    负责归属校验并构造这两个值。冻结字段只防止执行中误改，不能代替鉴权。
    恢复会话时需要重新提供 Context，不能从历史消息推断当前用户身份。

    数据库会话、模型客户端和密钥不放进 State；现有工具暂时仍通过闭包
    获取 db，后续接图时再安排工具调用的数据库会话生命周期。
    """

    user_id: int
    conversation_id: str
