"""第一版 MySQL 业务实体；导入不会创建表。"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, CheckConstraint, Computed, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from supportflow.db.base import Base, Timestamp, TimestampMixin
from supportflow.models.enums import (
    ApprovalDecision, FulfillmentStatus, PaymentStatus,
    RefundExecutionStatus, RefundStatus, UserRole,
)

# SQLite 变体仅用于离线约束测试，生产 MySQL 使用 BIGINT。
IdType = BigInteger().with_variant(Integer, "sqlite")


def enum_type(cls):
    return Enum(cls, native_enum=False, create_constraint=True,
                validate_strings=True, values_callable=lambda values: [v.value for v in values],
                name=cls.__name__.lower())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), comment="仅保存密码哈希")
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole), default=UserRole.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(default=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("paid_amount_cents >= 0", name="nonnegative_paid_amount"),
        Index("ix_orders_user_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    paid_amount_cents: Mapped[int] = mapped_column(BigInteger)
    payment_status: Mapped[PaymentStatus] = mapped_column(enum_type(PaymentStatus), default=PaymentStatus.UNPAID)
    fulfillment_status: Mapped[FulfillmentStatus] = mapped_column(enum_type(FulfillmentStatus), default=FulfillmentStatus.UNSHIPPED)
    paid_at: Mapped[datetime | None] = mapped_column(Timestamp)
    shipped_at: Mapped[datetime | None] = mapped_column(Timestamp)
    delivered_at: Mapped[datetime | None] = mapped_column(Timestamp)
    tracking_no: Mapped[str | None] = mapped_column(String(100))


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price_cents >= 0", name="nonnegative_unit_price"),
    )
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    product_code: Mapped[str] = mapped_column(String(64))
    product_name: Mapped[str] = mapped_column(String(200))
    product_model: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200), default="新会话")
    # id 同时作为 PostgreSQL checkpoint 的 thread_id，无跨数据库外键。


class RefundRequest(TimestampMixin, Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="positive_amount"),
        CheckConstraint("length(trim(reason_original)) > 0", name="nonblank_reason"),
        Index("ix_refund_requests_order_created", "order_id", "created_at"),
        Index("ix_refund_requests_status_created", "status", "created_at"),
    )
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True, comment="服务端稳定操作ID，重试复用")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="RESTRICT"), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    reason_original: Mapped[str] = mapped_column(Text)
    reason_category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[RefundStatus] = mapped_column(enum_type(RefundStatus), default=RefundStatus.PENDING)
    # MySQL UNIQUE 允许多个 NULL；拒绝后可重新申请，退款成功后永久占位。
    active_order_id: Mapped[int | None] = mapped_column(
        IdType, Computed("CASE WHEN status IN ('pending', 'approved', 'refunded') THEN order_id ELSE NULL END", persisted=True),
        unique=True,
    )


class RefundApproval(TimestampMixin, Base):
    __tablename__ = "refund_approvals"
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    refund_request_id: Mapped[int] = mapped_column(ForeignKey("refund_requests.id", ondelete="RESTRICT"), unique=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[ApprovalDecision] = mapped_column(enum_type(ApprovalDecision))
    comment: Mapped[str | None] = mapped_column(Text)


class RefundRecord(TimestampMixin, Base):
    __tablename__ = "refund_records"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="positive_amount"),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempts"),
    )
    id: Mapped[int] = mapped_column(IdType, primary_key=True)
    refund_request_id: Mapped[int] = mapped_column(ForeignKey("refund_requests.id", ondelete="RESTRICT"), unique=True)
    refund_no: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: str(uuid4()))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[RefundExecutionStatus] = mapped_column(enum_type(RefundExecutionStatus), default=RefundExecutionStatus.PROCESSING)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    succeeded_at: Mapped[datetime | None] = mapped_column(Timestamp)
