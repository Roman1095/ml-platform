from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.dataset import Dataset, DatasetVersion
from app.models.template import (
    TrainingTemplate,
    TrainingTemplateVersion,
)


async def seed_templates(session):
    templates = [
        {
            "name": "Scikit-learn Classification",
            "slug": "sklearn-classification",
            "description": (
                "Классификация табличных данных "
                "с использованием scikit-learn."
            ),
            "framework": "sklearn",
            "task_type": "classification",
            "entrypoint": "sklearn_classification",
            "parameter_schema": {
                "model": {
                    "type": "string",
                    "enum": [
                        "logistic_regression",
                        "random_forest",
                    ],
                },
                "test_size": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 0.5,
                },
                "random_state": {
                    "type": "integer",
                },
            },
            "default_parameters": {
                "model": "logistic_regression",
                "test_size": 0.2,
                "random_state": 42,
            },
        },
        {
            "name": "Scikit-learn Regression",
            "slug": "sklearn-regression",
            "description": (
                "Регрессия табличных данных "
                "с использованием scikit-learn."
            ),
            "framework": "sklearn",
            "task_type": "regression",
            "entrypoint": "sklearn_regression",
            "parameter_schema": {
                "model": {
                    "type": "string",
                    "enum": [
                        "linear_regression",
                        "random_forest",
                    ],
                },
                "test_size": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 0.5,
                },
                "random_state": {
                    "type": "integer",
                },
            },
            "default_parameters": {
                "model": "linear_regression",
                "test_size": 0.2,
                "random_state": 42,
            },
        },
    ]

    for item in templates:
        result = await session.execute(
            select(TrainingTemplate).where(
                TrainingTemplate.slug == item["slug"]
            )
        )

        template = result.scalar_one_or_none()

        if template is None:
            template = TrainingTemplate(
                name=item["name"],
                slug=item["slug"],
                description=item["description"],
                framework=item["framework"],
                task_type=item["task_type"],
                status="active",
            )

            session.add(template)
            await session.flush()

            version = TrainingTemplateVersion(
                template_id=template.id,
                version=1,
                entrypoint=item["entrypoint"],
                parameter_schema=item["parameter_schema"],
                default_parameters=item["default_parameters"],
                environment={
                    "python": "3.12",
                    "packages": [
                        "numpy",
                        "pandas",
                        "scikit-learn",
                        "joblib",
                        "skl2onnx",
                    ],
                },
                is_active=True,
            )

            session.add(version)


async def seed_datasets(session):
    datasets = [
        {
            "name": "Iris",
            "slug": "iris",
            "description": (
                "Классический датасет Iris ""для многоклассовой классификации."
            ),
            "metadata": {
                "sklearn_name": "iris",
                "task_type": "classification",
                "classes": 3,
            },
        },
        {
            "name": "Wine",
            "slug": "wine",
            "description": (
                "Wine dataset из scikit-learn."
            ),
            "metadata": {
                "sklearn_name": "wine",
                "task_type": "classification",
                "classes": 3,
            },
        },
        {
            "name": "Breast Cancer",
            "slug": "breast-cancer",
            "description": (
                "Breast Cancer Wisconsin dataset "
                "из scikit-learn."
            ),
            "metadata": {
                "sklearn_name": "breast_cancer",
                "task_type": "classification",
                "classes": 2,
            },
        },
        {
            "name": "Digits",
            "slug": "digits",
            "description": (
                "Набор изображений цифр "
                "из scikit-learn."
            ),
            "metadata": {
                "sklearn_name": "digits",
                "task_type": "classification",
                "classes": 10,
            },
        },
    ]

    for item in datasets:
        result = await session.execute(
            select(Dataset).where(
                Dataset.slug == item["slug"],
                Dataset.source_type == "builtin",
            )
        )

        dataset = result.scalar_one_or_none()

        if dataset is not None:
            continue

        dataset = Dataset(
            owner_user_id=None,
            name=item["name"],
            slug=item["slug"],
            source_type="builtin",
            status="available",
            framework="sklearn",
            description=item["description"],
            metadata_=item["metadata"],
        )

        session.add(dataset)
        await session.flush()

        version = DatasetVersion(
            dataset_id=dataset.id,
            version=1,
            storage_uri=None,
            checksum_sha256=None,
            size_bytes=None,
            sample_count=None,
            feature_count=None,
            target_count=None,
            metadata_=item["metadata"],
            status="available",
        )

        session.add(version)


async def main():
    async with AsyncSessionLocal() as session:
        await seed_templates(session)
        await seed_datasets(session)

        await session.commit()

    print("Seed completed successfully")


if __name__ == "__main__":
    asyncio.run(main())