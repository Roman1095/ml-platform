from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID


from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


dataset_source_type_enum = Enum(
    "builtin",
    "user",
    name="dataset_source_type",
    native_enum=True,
    create_type=False,
)


dataset_status_enum = Enum(
    "available",
    "processing",
    "disabled",
    "failed",
    name="dataset_status",
    native_enum=True,
    create_type=False,
)


dataset_version_status_enum = Enum(
    "available",
    "processing",
    "failed",
    "disabled",
    name="dataset_version_status",
    native_enum=True,
    create_type=False,
)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    slug: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(
        dataset_source_type_enum,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        dataset_status_enum,
        nullable=False,
        default="available",
    )

    framework: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="sklearn",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    storage_uri: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    sample_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    feature_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    target_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Важно: Python-имя metadata_ отличается от имени колонки metadata
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    status: Mapped[str] = mapped_column(
        dataset_version_status_enum,
        nullable=False,
        server_default=text("'available'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )