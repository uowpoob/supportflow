# 向量召回

入口：`src/supportflow/retrieval/search.py`，使用入库时相同的 Embedding 模型与维度。
只读取已有库和集合，不调用入库初始化、不新增或更新记录，也不生成回答。

## 命令行

```powershell
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.search "索尼 WH-1000XM5 没电后还能用有线模式听音乐吗？" --top-k 3
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.search "七天无理由退货的运费由谁承担？" --category policies
```

- `--top-k`：最多返回多少个片段，默认 5，范围 1～100。
- `--min-score`：最低 COSINE 相似度，默认 0.5，范围 -1～1。
- `--category`：可选 `data` 或 `policies`，省略则搜索两类文档。
- `--document-id`：指定文档 ID，可重复传入；省略则不限定文档。

正常无匹配输出 `count: 0`。配置、模型或数据库出错时以非零状态退出，不能当作正常无匹配。

## Python 调用

```python
from supportflow.retrieval.search import retrieve

chunks = await retrieve("耳机没电后还能有线聆听吗？", top_k=5, min_score=0.5)
```

返回字典列表，按 `score` 降序；每条包含 `document_id`、`chunk_id`、`title`、
`section`、`source`、`category`、`content` 和 `score`。
`content` 包含标题和正文，可以直接作为回答模型的证据；不返回大体积的向量。

流程：问题向量化 → 检查已有集合与向量维度 → 按入库模型、维度及可选条件过滤 →
Milvus COSINE Top-K → 丢弃低分结果 → 按 chunk_id 去重。
过滤值用 JSON 编码后构建表达式，不接受调用方传入任意 Milvus 表达式。
同步数据库调用在线程中执行，每次查询结束或失败后关闭客户端。

## 节点接入

`retrieve_knowledge` 读取当前 `knowledge.question`，必要时把 `product_model` 补入问题。
每次整体替换证据列表，不追加消息或复用上轮文档：

| 情况 | retrieval_status |
| --- | --- |
| 召回至少一个合格片段 | ready |
| 没有检索问题或没有合格片段 | empty |
| 配置、Embedding 或 Milvus 出错 | unavailable |

随后进入原有 `support_agent`，按本轮证据回答并引用来源。订单和退款业务仍走原有工具。

## 当前边界

- 这是稠密向量召回基线，尚未加入 BM25、RRF 和重排模型。
- 默认 0.5 是待校准的初始门槛，不是答案正确率；Top-K 候选也不保证足以回答。
- 当前资料没有统一的商品型号、政策版本或生效日期字段。型号只补进查询文本，
  不构成严格型号过滤；暂不支持政策版本、生效时间过滤。回答前仍须检查片段适用范围。
- 入库没有清理已删除条款，历史遗留片段仍可能被召回；需要后续完善语料同步。

离线测试覆盖排序与门槛、来源返回、过滤值转义、无匹配、模型与数据库故障、
客户端释放，以及节点三种状态和多轮证据隔离。

实现参考：[Milvus search API](https://milvus.io/api-reference/pymilvus/v3.0.x/MilvusClient/Vector/search.md)。
