from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_db
from app.models.template import (
    TrainingTemplate,
    TrainingTemplateVersion,
)
from app.schemas.catalog import (
    TemplateResponse,
    TemplateVersionResponse,
)


router = APIRouter(
    prefix="/api/templates",
    tags=["templates"],
)


@router.get(
    "",
    response_model=list[TemplateResponse],
)
async def list_templates(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrainingTemplate)
        .where(
            TrainingTemplate.status == "active"
        )
        .order_by(TrainingTemplate.name)
    )

    return list(result.scalars().all())


@router.get(
    "/{template_id}/versions",
    response_model=list[TemplateVersionResponse],
)
async def list_template_versions(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    template_result = await db.execute(
        select(TrainingTemplate).where(
            TrainingTemplate.id == template_id,
            TrainingTemplate.status == "active",
        )
    )

    template = template_result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    result = await db.execute(
        select(TrainingTemplateVersion)
        .where(
            TrainingTemplateVersion.template_id == template_id,
            TrainingTemplateVersion.is_active.is_(True),
        )
        .order_by(
            TrainingTemplateVersion.version.desc()
        )
    )

    return list(result.scalars().all())