from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Float

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


job_status_enum = Enum(
    "queued",
    "preparing",
    "running",
    "evaluating",
    "exporting",
    "completed",
    "failed",
    "cancelled",
    name="job_status",
    native_enum=True,
    create_type=False,
)

output_format_enum = Enum(
    "onnx",
    "pth",
    "joblib",
    name="output_format",
    native_enum=True,
    create_type=False,
)


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    template_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_template_versions.id"),
        nullable=False,
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id"),
        nullable=False,
    )

    worker_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        job_status_enum,
        nullable=False,
        server_default=text("'queued'"),
    )

    output_format: Mapped[str] = mapped_column(
        output_format_enum,
        nullable=False,
    )

    parameters: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    metrics_summary: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    progress_percent: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("0"),
    )

    current_epoch: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    total_epochs: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TrainingMetric(Base):
    __tablename__ = "training_metrics"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    epoch: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    step: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    metric_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    metric_value: Mapped[float] = mapped_column(
        # PostgreSQL DOUBLE PRECISION
        # SQLAlchemy Float здесь не нужен для первого MVP. Был numeric(20,10)
        Float,
        nullable=False,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TrainingLog(Base):
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'INFO'"),
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    epoch: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )