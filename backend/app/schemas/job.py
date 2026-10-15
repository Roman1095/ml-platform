from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OutputFormat = Literal["joblib", "onnx", "pth"]

JobStatus = Literal[
    "queued",
    "preparing",
    "running",
    "evaluating",
    "exporting",
    "completed",
    "failed",
    "cancelled",
]


class TrainingJobCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150)

    template_version_id: uuid.UUID

    dataset_version_id: uuid.UUID

    parameters: dict = Field(default_factory=dict)

    output_format: OutputFormat = "joblib"


class TrainingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID

    template_version_id: uuid.UUID
    dataset_version_id: uuid.UUID

    name: str | None

    status: JobStatus
    output_format: OutputFormat

    parameters: dict
    metrics_summary: dict

    progress_percent: float

    current_epoch: int | None
    total_epochs: int | None

    error_code: str | None
    error_message: str | None

    worker_node_id: uuid.UUID | None = None

    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    created_at: datetime
    updated_at: datetime


class TrainingMetricResponse(BaseModel):
    id: int
    epoch: int | None
    step: int | None
    metric_name: str
    metric_value: float
    recorded_at: datetime


class TrainingLogResponse(BaseModel):
    id: int
    level: str
    message: str
    epoch: int | None
    created_at: datetime


class ModelArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    version: int
    format: OutputFormat
    checksum_sha256: str | None
    size_bytes: int | None
    metrics: dict
    metadata: dict
    created_at: datetime