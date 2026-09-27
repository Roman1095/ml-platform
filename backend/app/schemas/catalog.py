from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    entrypoint: str
    parameter_schema: dict
    default_parameters: dict
    environment: dict
    is_active: bool
    created_at: datetime


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    framework: str
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class DatasetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    storage_uri: str | None
    checksum_sha256: str | None
    size_bytes: int | None
    sample_count: int | None
    feature_count: int | None
    target_count: int | None
    metadata: dict
    status: str
    created_at: datetime


class DatasetResponse(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    name: str
    slug: str | None
    source_type: str
    status: str
    framework: str
    description: str | None
    metadata: dict
    created_at: datetime
    updated_at: datetime
    versions: list[DatasetVersionResponse]