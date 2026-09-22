# BM25 召回

入口：`../src/supportflow/retrieval/retrieving/bm25.py`。从本地 `data/` 和 `policies/` 读取资料，
复用向量入库的 `load_documents()` / `split_documents()`，按条款建立内存索引。
不需要 Embedding、Milvus 或 `.env` 配置。

## 调用

```powershell
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.bm25 "WH-1000XM5 有线模式" --top-k 3
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.bm25 "无理由退货运费" --category policies
```

```python
from supportflow.retrieval.retrieving.bm25 import retrieve_bm25

chunks = await retrieve_bm25("WH-1000XM5 有线模式", top_k=5)
```

支持 `top_k`（默认 5，整数 1～100）、`category`（`data` / `policies`）和
`document_ids`（文档 ID 列表；空列表返回空结果）。命令行用可重复的 `--document-id`。
先筛选候选，再取 Top-K；IDF 和平均片段长度始终使用完整语料统计，不为过滤条件重新建索引。

## 检索过程

1. 文档和查询都做 NFKC 全半角归一化、英文小写化；中文使用 jieba 搜索分词。
   `WH-1000XM5`、`USB-C` 等连续英文/数字连字符词保持完整，过滤标点与空白。
2. 使用 `BM25Okapi`（`k1=1.5`，`b=0.75`，其余使用库默认值）计算词项匹配分数。
3. 排除与查询完全没有词项交集的片段；分数降序，同分按 `chunk_id` 排序。
4. 返回最多 Top-K 个片段，字段与向量召回相同：`document_id`、`chunk_id`、`title`、
   `section`、`source`、`category`、`content`、`score`。

`score` 是原始 BM25 分数，不是概率，也不是 COSINE 相似度；不能套用向量召回的 0.5 门槛
或直接将两路分数相加。Okapi 在很小的语料中也可能给匹配结果零分或负分，因此这里使用
词项交集判断是否匹配，不设固定最低分。词项重合仅代表召回候选，不保证能回答问题。

正常无匹配返回 `[]`；缺失目录、资料格式错误或无法建立索引时抛出共用的
`RetrievalUnavailable`，命令行非零退出。读取、分词、建索引和搜索都在线程中执行。

## 索引生命周期与混合检索

第一次查询时建立索引，同一进程后续查询复用；没有持久化文件。
修改、增加、删除本地资料后重启服务，或在没有在途检索时调用 `clear_index_cache()`，
下一次查询会重建。多进程部署时每个进程有独立缓存。

本入口仍可独立调用；图节点已通过 [混合召回与 RRF](hybrid-retrieval.md) 并发调用 BM25 与向量召回。
两路对同一份资料使用相同 `chunk_id`，融合时用于识别同一片段。
BM25 读取当前本地资料，向量检索读取最近入库的 Milvus 数据；更新资料时应同步向量入库，
已有向量入库流程尚不清理已删除条款，融合前仍需处理语料版本一致性。

实现参考：[rank-bm25](https://github.com/dorianbrown/rank_bm25)、
[jieba](https://github.com/fxsjy/jieba)。
