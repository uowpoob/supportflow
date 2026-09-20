"""数据访问层（repository）：项目里**唯一**直接写 SQL、直接碰数据库会话的地方。

分层是一条直线，依赖只能往下走：

    api/  ·  agents/            收参、鉴权、翻异常
        ↓
    services/                   规则与事务边界
        ↓
    repository/                 SQL（本层）
        ↓
    models/                     表结构与枚举

## 这一层的规矩

1. **只拼 SQL、只碰会话，不判业务。** "能不能退""该不该拒""重试怎么办"全在
   `services/`；这里只回答"数据长什么样"。
2. **每个函数第一个参数都是 `db: AsyncSession`**，由调用方传进来。本层不自己开会话 ——
   自己开一个就等于把一件事务拆成两段，`services/` 那边的事务语义立刻失效。
3. **绝对不许 import `services/`。** 依赖反向会立刻造出循环 import
   （`services/refunds/types.py` 那种被 `schemas/` 引用的文件最容易被拽进去）。

## 一个新查询该写在哪边

一句话：**"向数据库要什么"→ 这里；"拿到之后怎么判断"→ `services/`。**

`services/orders.py`、`services/refunds/queries.py` 现在是转发入口，
保持它们名字不变是为了让路由和 Agent Tool 一行都不用改。
"""
