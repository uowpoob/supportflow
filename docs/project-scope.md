# SupportFlow 项目约定 v0.2

目标：完成可部署、可评测、能解释设计取舍的售后 Agent 面试项目。逐步开发，每一步先验收再进入下一步。

## 功能与边界

客户：订单查询、政策咨询、退款申请、进度查询、多轮会话。管理员：审批退款。
模型理解诉求、选择工具和组织回答；后端决定权限、资格、金额和写入。
只使用模拟用户、订单、政策和退款，不接真实支付。首版不做换货或多企业租户。

## 技术栈与安装顺序

| 阶段 | 技术 | 验收 |
| --- | --- | --- |
| 当前：最小服务 | Python 3.13、uv、FastAPI、Pydantic、Uvicorn | GET /health 返回 200 |
| 业务 API | MySQL、SQLAlchemy、Alembic、MySQL 驱动、pytest | 查询本人订单，拒绝越权 |
| 最小 Agent | LangGraph、LangChain 必要组件、模型适配器 | 识别意图、追问、查订单 |
| 检索 | Milvus、Embedding、BM25、RRF、Reranker | 比较向量、混合、混合加重排序 |
| 审批与恢复 | PostgreSQL checkpoint、MySQL 事务与唯一约束 | 重启可恢复、并发不重复退款 |
| 界面部署 | React、TypeScript、Vite、SSE、Docker Compose | 浏览器完成业务闭环 |
| 评测 | LangSmith、pytest、固定数据集、GitHub Actions | 可复现的报告与自动检查 |

模型、Embedding、Reranker 型号尚未确定。基础服务不需要 API Key。
桌面 requirements.txt 是参考清单，不整体导入：Milvus 组件可按需采用，解析和本地推理组件暂不需要；后续还需 MySQL 驱动和 Alembic，并验证版本兼容。
依赖以 pyproject.toml 为入口，uv.lock 记录解析后的精确版本。

## 模拟退款规则（本项目的初始设计，不是真实商家政策）

- 政策版本 demo-refund-v1：仅支持已支付、已签收的模拟订单全额退款。
- 申请时距离签收时间在 0 至 14 × 24 小时内（含边界）；时间统一为 UTC。
- 订单必须属于当前登录客户；不存在和无权限均不披露订单详情。
- 原因不能为空；订单号或原因缺失时追问。
- 金额取数据库实付金额，以整数分保存，不接受模型指定金额。
- 同一订单最多存在一个待审批或已批准的申请；已退款订单不能再次退款。
- 申请通过资格检查后进入 pending；管理员才能批准或拒绝。
- 批准后执行模拟退款；退款记录以申请 ID 唯一约束保证幂等。
- 重试不能重复扣款；执行失败保留可重试状态，不标记退款成功。
- 资格按申请时间判断；执行前再次检查归属、支付状态、实付金额及是否已退款。

## 隔离与证据

服务端从认证身份获取用户，不信任请求中的 user_id。访问会话与订单都检查归属。
conversation_id 对应独立图状态；thread_id 本身不是认证机制。
检索过滤商品与政策版本；回答附文档、条款、版本，无依据时追问或转人工。

## 评测口径（目标，尚无实测结果）

意图 Accuracy ≥90%、Macro-F1 ≥0.88；Recall@5 ≥85%；回答级幻觉率 ≤5%；
端到端成功率 ≥85%；无证据处理正确率 ≥90%；所有定义的隔离及幂等用例通过。
Recall@5 按每个问题的相关片段召回比例取平均；幻觉指回答包含至少一处无依据或矛盾事实。
同时报告回答覆盖率、P50/P95 延迟、Token 与成本。数值置信度需独立校准，不把相似度当正确概率。
分层验收矩阵是开发规范，不是独立测试集，也不代表已有成绩。
后续另建人工审核的保留测试集，报告版本、模型、样本数、分子与分母；LangSmith 裁判需人工抽样复核。

## 存储职责与一致性

| 存储 | 权威数据 | 边界 |
| --- | --- | --- |
| MySQL | 用户、订单、会话归属、退款申请、原始退款原因及结构化分类、审批、模拟退款流水 | 业务事实与权限的唯一权威来源 |
| PostgreSQL | LangGraph 消息与节点状态、checkpoint、暂停恢复信息 | 业务摘要不能作为退款成功或权限的依据 |
| Milvus | 政策片段、稠密向量、BM25稀疏表示、文档/条款/版本/商品元数据 | 从版本化政策源重建的索引，不保存权威交易记录 |

会话列表和 user_id → conversation_id 归属在 MySQL，图上下文在 PostgreSQL。先校验归属再读取 checkpoint，不接受客户端任意指定 thread_id。
退款原因即便在消息中出现，提交申请时仍要写入 MySQL，保留原文并另存规范化分类。
MySQL 业务事务和 PostgreSQL checkpoint 不构成一个原子事务。先按稳定业务操作ID在 MySQL 幂等提交，再更新图状态；checkpoint 失败后，恢复流程查询已提交结果，不能重新退款。
审批和退款状态以 MySQL 为准，恢复图时重新核对。模拟退款流水和业务状态在同一个 MySQL 事务中提交；同订单有效申请和同申请退款均需数据库级并发约束。
代价是维护三种存储，增加部署、备份和故障排查工作。分阶段启动：业务阶段 MySQL，Agent持久化阶段 PostgreSQL，检索阶段 Milvus。

## Milvus 检索路线

稠密召回基线 → 加 BM25 词项召回与 RRF 融合 → 评估 Reranker。
中文分析器、精确商品型号、否定词、政策版本、生效时间要单独验证；具体服务版本与部署资源在检索阶段确定。
政策源在仓库版本管理，明确文档、条款、版本、生效时间，区分现行与历史适用政策。
参考：[LangGraph checkpoint 集成](https://docs.langchain.com/oss/python/integrations/checkpointers)、[Milvus 混合检索](https://milvus.io/docs/multi-vector-search.md)、[BM25 全文检索](https://milvus.io/docs/full-text-search.md)。
