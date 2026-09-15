"""所有业务实体共用的声明式基类。"""
from datetime import datetime, timezone
from sqlalchemy import MetaData
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """MySQL DATETIME 不保存时区，统一写入 UTC 无时区时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


Timestamp = DateTime().with_variant(DATETIME(fsp=6), "mysql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(Timestamp, default=utc_now, onupdate=utc_now)
