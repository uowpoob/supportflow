"""登录会话配置；本地 HTTP 开发与生产 HTTPS 可分别配置 Cookie。"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from supportflow.core.database import PROJECT_ROOT

SESSION_COOKIE_NAME = "supportflow_session"


class AuthSettings(BaseSettings):
    # 会话有效期：1 小时。
    SESSION_TTL_SECONDS: int = Field(default=3600, gt=0)
    SESSION_COOKIE_SECURE: bool = False  # 本地 HTTP；生产 HTTPS 必须设为 true。

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )


auth_settings = AuthSettings()
