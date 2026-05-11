"""Initial schema: tenant, box, pairing_code, cert, audit.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("license_key", sa.String(255), nullable=True),
        sa.Column("license_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("plan", sa.String(32), server_default="free", nullable=False),
        sa.Column("box_quota", sa.Integer, server_default="5", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "box",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id"),
            nullable=True,
        ),
        sa.Column("serial_number", sa.String(255), nullable=False, unique=True),
        sa.Column("paired_db_uuid", sa.String(64), nullable=True),
        sa.Column("paired_server_url", sa.String(512), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cert_subject", sa.String(255), nullable=True),
        sa.Column("cert_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tunnel_subdomain", sa.String(64), nullable=True),
        sa.Column("box_token", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_box_serial_number", "box", ["serial_number"])

    op.create_table(
        "pairing_code",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column(
            "box_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("box.id"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_db_uuid", sa.String(64), nullable=True),
    )

    op.create_table(
        "cert",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "box_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("box.id"),
            nullable=False,
        ),
        sa.Column("pem", sa.Text, nullable=False),
        sa.Column("private_key_encrypted", sa.Text, nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "issuer", sa.String(64), server_default="lets-encrypt-r12", nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id"),
            nullable=True,
        ),
        sa.Column(
            "box_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("box.id"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_audit_ts", "audit", ["ts"])
    op.create_index("ix_audit_box_id", "audit", ["box_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_box_id", table_name="audit")
    op.drop_index("ix_audit_ts", table_name="audit")
    op.drop_table("audit")
    op.drop_table("cert")
    op.drop_table("pairing_code")
    op.drop_index("ix_box_serial_number", table_name="box")
    op.drop_table("box")
    op.drop_table("tenant")
