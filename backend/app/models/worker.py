from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    Enum as SAEnum,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class WorkerNode(Base):
    __tablename__ = "worker_nodes"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    name = Column(
        String(120),
        nullable=False,
        unique=True,
    )

    hostname = Column(
        String(255),
        nullable=True,
    )

    platform = Column(
        String(50),
        nullable=True,
    )

    architecture = Column(
        String(50),
        nullable=True,
    )

    cpu_cores = Column(
        Integer,
        nullable=True,
    )

    memory_bytes = Column(
        BigInteger,
        nullable=True,
    )

    status = Column(
        SAEnum(
            "online",
            "offline",
            "busy",
            "maintenance",
            name="worker_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'offline'"),
    )

    capabilities = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    last_heartbeat_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )