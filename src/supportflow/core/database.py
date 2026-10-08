"""数据库独立配置：迁移不依赖模型 API 密钥或追踪服务。"""
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DatabaseSettings(BaseSettings):
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = Field(default=3306, ge=1, le=65535)
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: SecretStr = SecretStr("")
    MYSQL_DATABASE: str = "agent_project"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+asyncmy",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD.get_secret_value(),
            host=self.MYSQL_HOST, port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE, query={"charset": "utf8mb4"},
        )
