from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.schemas.catalog import (
    DatasetResponse,
    DatasetVersionResponse,
)


router = APIRouter(
    prefix="/api/datasets",
    tags=["datasets"],
)


@router.get(
    "",
    response_model=list[DatasetResponse],
)
async def list_datasets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset)
        .where(
            Dataset.status == "available",
            or_(
                Dataset.source_type == "builtin",
                Dataset.owner_user_id == current_user.id,
            ),
        )
        .order_by(Dataset.name)
    )

    datasets = list(result.scalars().all())

    response: list[DatasetResponse] = []

    for dataset in datasets:
        versions_result = await db.execute(
            select(DatasetVersion)
            .where(
                DatasetVersion.dataset_id == dataset.id,
                DatasetVersion.status == "available",
            )
            .order_by(
                DatasetVersion.version.desc()
            )
        )

        versions = list(
            versions_result.scalars().all()
        )

        response.append(
            DatasetResponse(
                id=dataset.id,
                owner_user_id=dataset.owner_user_id,
                name=dataset.name,
                slug=dataset.slug,
                source_type=dataset.source_type,
                status=dataset.status,
                framework=dataset.framework,
                description=dataset.description,
                metadata=dataset.metadata_,
                created_at=dataset.created_at,
                updated_at=dataset.updated_at,
                versions=[
                    DatasetVersionResponse(
                        id=version.id,
                        version=version.version,
                        storage_uri=version.storage_uri,
                        checksum_sha256=version.checksum_sha256,
                        size_bytes=version.size_bytes,
                        sample_count=version.sample_count,
                        feature_count=version.feature_count,
                        target_count=version.target_count,
                        metadata=version.metadata_,
                        status=version.status,
                        created_at=version.created_at,
                    )
                    for version in versions
                ],
            )
        )

    return response


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
)
async def get_dataset(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.status == "available",
            or_(
                Dataset.source_type == "builtin",
                Dataset.owner_user_id == current_user.id,
            ),
        )
    )

    dataset = result.scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )

    versions_result = await db.execute(
        select(DatasetVersion)
        .where(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.status == "available",
        )
        .order_by(
            DatasetVersion.version.desc()
        )
    )

    versions = list(
        versions_result.scalars().all()
    )

    return DatasetResponse(
        id=dataset.id,
        owner_user_id=dataset.owner_user_id,
        name=dataset.name,
        slug=dataset.slug,
        source_type=dataset.source_type,
        status=dataset.status,
        framework=dataset.framework,
        description=dataset.description,
        metadata=dataset.metadata_,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        versions=[
            DatasetVersionResponse(
                id=version.id,
                version=version.version,
                storage_uri=version.storage_uri,
                checksum_sha256=version.checksum_sha256,
                size_bytes=version.size_bytes,
                sample_count=version.sample_count,
                feature_count=version.feature_count,
                target_count=version.target_count,
                metadata=version.metadata_,
                status=version.status,
                created_at=version.created_at,
            )
            for version in versions
        ],
    )