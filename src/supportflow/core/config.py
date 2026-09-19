from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr, field_validator
from pydantic_settings import SettingsConfigDict
from supportflow.core.database import DatabaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# pydantic-settings 只把 .env 读进 Settings 对象，不会写入 os.environ；
# 而 LangChain / LangSmith 的 tracer 只认进程环境变量，这里补上这一步。
# override=False 保证已存在的系统环境变量优先，.env 仅作兜底。
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
    # 只允许 text-embedding-v4 实际支持的档位，避免建 Milvus 集合时 dim 与模型不一致。
    # 注意：不能写成 Literal[64, ...] —— 环境变量读进来是字符串 "1024"，
    # Literal 不做类型转换会直接校验失败，必须用 int + 校验器。
    EMBEDDING_DIM: int = 1024

    # 阿里云百炼文本重排（rerank），走 DashScope 原生接口，不是 OpenAI 兼容模式。
    # 实测（2026-09-15）：通用域名可直接调用，官方文档里的 {WorkspaceId}.cn-beijing.maas
    # 域名并非必需。完整端点 = f"{DASHSCOPE_NATIVE_BASE_URL}/services/rerank/text-rerank/text-rerank"
    DASHSCOPE_NATIVE_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    RERANK_MODEL: str = "gte-rerank-v2"

    LANGSMITH_TRACING: bool
    LANGSMITH_ENDPOINT: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str

    # LangGraph 对话记忆（checkpoint）用的 PostgreSQL 连接串，跑在 Docker 里。
    # 与业务库 MySQL 分开：MySQL 存业务数据并负责归属校验，Postgres 只存对话历史，
    # 两边靠 thread_id（= conversations 表的主键）关联，没有跨库外键。
    # 给个空默认值：本机没起 Postgres 时，只要不去建 checkpointer 就不会报错。
    LANGGRAPH_PG_DSN: str = ""

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
