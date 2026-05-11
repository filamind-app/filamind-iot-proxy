"""SQLAlchemy ORM models — mirrors the Postgres schema (Alembic 0001)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    box_quota: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    boxes: Mapped[list["Box"]] = relationship(back_populates="tenant")


class Box(Base):
    __tablename__ = "box"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.id"), nullable=True,
    )
    serial_number: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False,
    )
    paired_db_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paired_server_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cert_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cert_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tunnel_subdomain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    box_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    tenant: Mapped[Tenant | None] = relationship(back_populates="boxes")


class PairingCode(Base):
    """Pairing codes are persisted in Postgres (truth) AND mirrored to
    Redis with TTL for fast polling lookups. Postgres row survives even
    after Redis evicts the cache entry."""

    __tablename__ = "pairing_code"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    box_id: Mapped[UUID] = mapped_column(ForeignKey("box.id"), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    consumed_by_db_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Cert(Base):
    """Per-box LE cert. Phase 2 populates this — Phase 1 only defines
    the schema."""

    __tablename__ = "cert"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    box_id: Mapped[UUID] = mapped_column(ForeignKey("box.id"), nullable=False)
    pem: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issuer: Mapped[str] = mapped_column(
        String(64), default="lets-encrypt-r12", nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class Audit(Base):
    """Append-only audit log. Anyone with a status mutation writes a row."""

    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.id"), nullable=True,
    )
    box_id: Mapped[UUID | None] = mapped_column(ForeignKey("box.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
