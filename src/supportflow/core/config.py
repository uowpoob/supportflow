from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# pydantic-settings 只把 .env 读进 Settings 对象，不会写入 os.environ；
# 而 LangChain / LangSmith 的 tracer 只认进程环境变量，这里补上这一步。
# override=False 保证已存在的系统环境变量优先，.env 仅作兜底。
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = Field(default=3306, ge=1, le=65535)
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: SecretStr = SecretStr("")
    MYSQL_DATABASE: str = "agent_project"

    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    LANGSMITH_TRACING: bool
    LANGSMITH_ENDPOINT: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"

    )


settings = Settings()
