from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.services.artifacts import (
    artifact_download_filename,
    resolve_stored_artifact_path,
    sha256_file,
)
from app.models.artifact import ModelArtifact
from app.models.dataset import Dataset, DatasetVersion
from app.models.job import TrainingJob, TrainingLog, TrainingMetric
from app.models.template import TrainingTemplate, TrainingTemplateVersion
from app.models.user import User
from app.services.job_lifecycle import JobStateError, is_cancellable

from app.schemas.job import (
    ModelArtifactResponse,
    TrainingJobCreateRequest,
    TrainingJobResponse,
    TrainingLogResponse,
    TrainingMetricResponse,
)

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"],
)


async def get_job_for_user(
    job_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> TrainingJob:
    result = await db.execute(
        select(TrainingJob).where(
            TrainingJob.id == job_id,
            TrainingJob.owner_user_id == current_user.id,
        )
    )

    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training job not found",
        )

    return job


@router.post(
    "",
    response_model=TrainingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    payload: TrainingJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrainingJob:
    # ---------------------------------------------------------
    # 1. Получаем template version
    # ---------------------------------------------------------

    template_version_result = await db.execute(
        select(TrainingTemplateVersion).where(
            TrainingTemplateVersion.id == payload.template_version_id,
            TrainingTemplateVersion.is_active.is_(True),
        )
    )

    template_version = template_version_result.scalar_one_or_none()

    if template_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template version not found or inactive",
        )

    # ---------------------------------------------------------
    # 2. Проверяем, что template активен
    # ---------------------------------------------------------

    template_result = await db.execute(
        select(TrainingTemplate).where(
            TrainingTemplate.id == template_version.template_id,
            TrainingTemplate.status == "active",
        )
    )

    template = template_result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template is not active",
        )

    # ---------------------------------------------------------
    # 3. Проверяем dataset version
    # ---------------------------------------------------------

    dataset_version_result = await db.execute(
        select(DatasetVersion).where(
            DatasetVersion.id == payload.dataset_version_id,
            DatasetVersion.status == "available",
        )
    )

    dataset_version = dataset_version_result.scalar_one_or_none()

    if dataset_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset version not found or unavailable",
        )

    # ---------------------------------------------------------
    # 4. Проверяем доступ пользователя к dataset
    # ---------------------------------------------------------

    dataset_result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_version.dataset_id,
            Dataset.status == "available",
        )
    )

    dataset = dataset_result.scalar_one_or_none()

    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )

    if (
        dataset.source_type != "builtin"
        and dataset.owner_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this dataset",
        )

    # ---------------------------------------------------------
    # 5. Параметры.
    #
    # Defaults из template + параметры пользователя.
    # ---------------------------------------------------------

    parameters = {
        **(template_version.default_parameters or {}),
        **payload.parameters,
    }

    # ---------------------------------------------------------
    # 6. Пока первый vertical slice поддерживает joblib.
    # ---------------------------------------------------------

    if payload.output_format != "joblib":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Only 'joblib' output is currently supported "
                "by the sklearn worker"
            ),
        )

    # ---------------------------------------------------------
    # 7. Создаём job
    # ---------------------------------------------------------

    job = TrainingJob(
        owner_user_id=current_user.id,
        template_version_id=template_version.id,
        dataset_version_id=dataset_version.id,
        name=payload.name,
        status="queued",
        output_format=payload.output_format,
        parameters=parameters,
        metrics_summary={},
        progress_percent=0,
        queued_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(job)

    await db.commit()
    await db.refresh(job)

    return job


@router.get(
    "",
    response_model=list[TrainingJobResponse],
)
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TrainingJob]:
    result = await db.execute(
        select(TrainingJob)
        .where(TrainingJob.owner_user_id == current_user.id)
        .order_by(TrainingJob.created_at.desc())
    )

    return list(result.scalars().all())


@router.get(
    "/{job_id}",
    response_model=TrainingJobResponse,
)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrainingJob:
    return await get_job_for_user(job_id, current_user, db)


@router.get(
    "/{job_id}/metrics",
    response_model=list[TrainingMetricResponse],
)
async def get_job_metrics(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_job_for_user(job_id, current_user, db)

    result = await db.execute(
        select(TrainingMetric)
        .where(TrainingMetric.job_id == job_id)
        .order_by(
            TrainingMetric.recorded_at.asc(),
            TrainingMetric.id.asc(),
        )
    )

    return [
        TrainingMetricResponse(
            id=metric.id,
            epoch=metric.epoch,
            step=metric.step,
            metric_name=metric.metric_name,
            metric_value=float(metric.metric_value),
            recorded_at=metric.recorded_at,
        )
        for metric in result.scalars().all()
    ]


@router.get(
    "/{job_id}/logs",
    response_model=list[TrainingLogResponse],
)
async def get_job_logs(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_job_for_user(job_id, current_user, db)

    result = await db.execute(
        select(TrainingLog)
        .where(TrainingLog.job_id == job_id)
        .order_by(
            TrainingLog.created_at.asc(),
            TrainingLog.id.asc(),
        )
    )

    return [
        TrainingLogResponse(
            id=log.id,level=log.level,
            message=log.message,
            epoch=log.epoch,
            created_at=log.created_at,
        )
        for log in result.scalars().all()
    ]


@router.get(
    "/{job_id}/artifacts",
    response_model=list[ModelArtifactResponse],
)
async def get_job_artifacts(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_job_for_user(job_id, current_user, db)

    result = await db.execute(
        select(ModelArtifact)
        .where(ModelArtifact.job_id == job_id)
        .order_by(ModelArtifact.created_at.desc())
    )

    return [
        ModelArtifactResponse(
            id=artifact.id,
            job_id=artifact.job_id,
            owner_user_id=artifact.owner_user_id,
            name=artifact.name,
            version=artifact.version,
            format=artifact.format,
            checksum_sha256=artifact.checksum_sha256,
            size_bytes=artifact.size_bytes,
            metrics=artifact.metrics_,
            metadata=artifact.metadata_,
            created_at=artifact.created_at,
        )
        for artifact in result.scalars().all()
    ]


@router.get(
    "/{job_id}/artifacts/{artifact_id}/download",
)
async def download_job_artifact(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ModelArtifact).where(
            ModelArtifact.id == artifact_id,
            ModelArtifact.job_id == job_id,
            ModelArtifact.owner_user_id == current_user.id,
        )
    )

    artifact = result.scalar_one_or_none()

    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    path = resolve_stored_artifact_path(artifact.storage_uri)

    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file not found",
        )

    if artifact.checksum_sha256 is not None:
        actual_checksum = sha256_file(path)

        if actual_checksum != artifact.checksum_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Artifact checksum mismatch",
            )

    filename = artifact_download_filename(
        artifact.job_id,
        artifact.format,
    )

    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=filename,
        content_disposition_type="attachment",
    )


@router.post(
    "/{job_id}/cancel",
    response_model=TrainingJobResponse,
)
async def cancel_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Lock the row so cancellation cannot race with the worker's
    # final transition to a terminal state.
    result = await db.execute(
        select(TrainingJob)
        .where(
            TrainingJob.id == job_id,
            TrainingJob.owner_user_id == current_user.id,
        )
        .with_for_update()
    )

    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training job not found",
        )

    if not is_cancellable(job.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel job in status '{job.status}'",
        )

    try:
        from app.services.job_lifecycle import transition_or_raise

        transition_or_raise(job.status, "cancelled")
    except JobStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)

    db.add(
        TrainingLog(
            job_id=job.id,
            level="INFO",
            message="Job cancelled by user",
        )
    )

    await db.commit()
    await db.refresh(job)

    return job
