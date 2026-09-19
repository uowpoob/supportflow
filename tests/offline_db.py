"""测试用的离线数据库：内存 SQLite + 把同步会话包装成异步接口。

**为什么不用 Mock**：`AsyncSession` 一旦被 Mock，`where` 条件写错也测不出来 ——
Mock 会老老实实返回你喂给它的那个对象。这里**真的执行 SQL**，所以"归属条件少写
一个 `user_id`"这类错误会当场失败。跨用户隔离那类断言只有这样才能成立。

局限（用之前先看一眼）：
- 仅供**顺序**测试。它没有并发语义，MySQL 的 `SELECT ... FOR UPDATE` 到这里是空操作 ——
  并发相关的结论必须在真库上验证。
- SQLite 与 MySQL 的差异（生成列 `GENERATED ALWAYS AS`、字符集与排序规则）不在覆盖范围内，
  那些由迁移测试和真机验收负责。
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import supportflow.models  # noqa: F401  建表前必须导入，否则 Base.metadata 里一张表都没有
from supportflow.db.base import Base


def make_engine():
    """建一个空的内存 SQLite 库，并按模型建好全部表。"""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        # SQLite 默认不检查外键，不打开的话 FK 约束形同虚设。
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


class OfflineSession:
    """把同步 `Session` 包成业务层期望的 `AsyncSession` 形状。

    只转发业务层实际用到的那几个方法，不做任何业务判断 ——
    逻辑都在被测代码里，这里多写一行都可能把问题盖住。

    `expire_on_commit=False` 由调用方在构造 `Session` 时负责，
    否则 commit 之后对象属性会过期，异步环境里再读会抛 `MissingGreenlet`。
    """

    def __init__(self, session: Session):
        self.session = session

    def add(self, value):
        self.session.add(value)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, value):
        self.session.refresh(value)
