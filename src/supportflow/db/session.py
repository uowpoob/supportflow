"""MySQL 连接与请求级会话；导入模块时不连接或创建表。"""

from collections.abc import Generator

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

from supportflow.core.config import settings

# URL.create 保留密码中的 @、/ 等特殊字符，也支持库名中的空格。
database_url = URL.create(
    drivername="mysql+pymysql",
    username=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD.get_secret_value(),
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    database=settings.MYSQL_DATABASE,
    query={"charset": "utf8mb4"},
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """供 FastAPI Depends 使用；写操作由业务层显式提交。"""
    with SessionLocal() as session:
        yield session
