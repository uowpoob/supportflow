from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import SettingsConfigDict
from supportflow.core.database import DatabaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# pydantic-settings 不写入 os.environ，但 LangChain/LangSmith tracer 只认进程环境变量，故补 load_dotenv。
# override=False：已存在的系统环境变量优先，.env 仅作兜底。
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(DatabaseSettings):
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # 阿里云百炼（DashScope）文本向量，走 OpenAI 兼容模式。
    # 用 SecretStr：密钥不会出现在日志或报错信息里，取用需显式 get_secret_value()。
    DASHSCOPE_API_KEY: SecretStr = SecretStr("")
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v4"
    # 只允许 text-embedding-v4 实际支持的档位，避免 Milvus 集合 dim 与模型不一致。
    # 不能写 Literal[...]：环境变量读进来是字符串 "1024"，Literal 不做转换会校验失败，必须用 int + 校验器。
    EMBEDDING_DIM: int = 1024

    # 重排共用该服务地址；Qwen3 适配器转换为 /compatible-api/v1/reranks。
    DASHSCOPE_NATIVE_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    RERANK_MODEL: str = "qwen3-rerank"

    # 是否在 RRF 融合之后再过一遍重排（融合只看名次，重排按语义）。
    # 关掉可省掉检索链路上唯一的外部依赖；rerank 自身失败时也会退回融合顺序。
    RETRIEVAL_RERANK: bool = True

    # JSON 快照保存全部 BM25 统计；相对路径以项目根目录为基准。
    BM25_INDEX_PATH: Path = PROJECT_ROOT / ".local" / "indexes" / "bm25.json"

    # 本地知识库无结果或不可用时，搜索网上公开资料；不配置密钥则如实降级。
    TAVILY_API_KEY: SecretStr = SecretStr("")
    TAVILY_BASE_URL: str = "https://api.tavily.com"
    WEB_SEARCH_MAX_RESULTS: int = Field(default=5, ge=1, le=10)
    WEB_SEARCH_TIMEOUT_SECONDS: float = Field(default=15, gt=0, le=60)

    # LangSmith 为可选观测工具，全部给默认值：缺省也能启动/导入，不必强制配置。
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "supportflow"

    # LangGraph checkpoint 用的 PostgreSQL（Docker）。与业务库 MySQL 分开：
    # MySQL 存业务数据并做归属校验，Postgres 只存对话历史，两边靠 thread_id 关联，无跨库外键。
    # 空默认值：本机没起 Postgres 时，不建 checkpointer 就不会报错。
    LANGGRAPH_PG_DSN: str = ""
    MILVUS_URI: str = ""
    DB_NAME: str
    COLLECTION: str


    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"

    )

    @field_validator("EMBEDDING_DIM")
    @classmethod
    def _validate_embedding_dim(cls, value: int) -> int:
        allowed = {64, 128, 256, 512, 768, 1024, 1536, 2048}
        if value not in allowed:
            raise ValueError(
                f"text-embedding-v4 只支持 {sorted(allowed)}，当前值为 {value}"
            )
        return value


settings = Settings()
