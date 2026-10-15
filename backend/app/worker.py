from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
import sys
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.datasets import (
    load_breast_cancer,
    load_digits,
    load_iris,
    load_wine,
)
from sklearn.ensemble import (
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    LinearRegression,
    LogisticRegression,
)
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.svm import SVC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.artifact import ModelArtifact
from app.models.dataset import Dataset, DatasetVersion
from app.models.job import TrainingJob, TrainingLog, TrainingMetric
from app.models.template import TrainingTemplateVersion
from app.models.worker import WorkerNode
from app.services.artifacts import sha256_file
from app.services.job_lifecycle import JobStateError, transition_or_raise


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("ml-platform-worker")

WORKER_CAPABILITIES = {
    "frameworks": ["sklearn"],
    "output_formats": ["joblib"],
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def read_memory_bytes() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    kilobytes = int(line.split()[1])
                    return kilobytes * 1024
    except (OSError, ValueError, IndexError):
        return None

    return None


def load_builtin_dataset(name: str):
    loaders = {
        "iris": load_iris,
        "wine": load_wine,
        "breast_cancer": load_breast_cancer,
        "digits": load_digits,
    }

    loader = loaders.get(name)

    if loader is None:
        raise ValueError(
            f"Unsupported sklearn dataset: {name}"
        )

    dataset = loader()

    return dataset.data, dataset.target


def create_classification_model(
    name: str,
    params: dict,
):
    random_state = int(
        params.get("random_state", 42)
    )

    if name == "logistic_regression":
        return LogisticRegression(
            max_iter=int(
                params.get("max_iter", 1000)
            ),
            random_state=random_state,
        )

    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=int(
                params.get("n_estimators", 100)
            ),
            max_depth=(
                int(params["max_depth"])
                if params.get("max_depth") is not None
                else None
            ),
            random_state=random_state,
        )

    if name == "svm":
        return SVC(
            C=float(params.get("C", 1.0)),
            kernel=str(params.get("kernel", "rbf")),
            random_state=random_state,
        )

    raise ValueError(
        f"Unsupported classification model: {name}"
    )


def create_regression_model(
    name: str,
    params: dict,
):
    random_state = int(
        params.get("random_state", 42)
    )

    if name == "linear_regression":
        return LinearRegression()

    if name == "random_forest":
        return RandomForestRegressor(
            n_estimators=int(
                params.get("n_estimators", 100)
            ),
            max_depth=(
                int(params["max_depth"])
                if params.get("max_depth") is not None
                else None
            ),
            random_state=random_state,
        )

    raise ValueError(
        f"Unsupported regression model: {name}"
    )


def export_joblib_artifact(model, path: Path) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return path.stat().st_size, sha256_file(path)


async def write_log(
    db: AsyncSession,
    job_id: uuid.UUID,
    message: str,
    level: str = "INFO",
    epoch: int | None = None,
):
    db.add(
        TrainingLog(
            job_id=job_id,
            level=level,
            message=message,
            epoch=epoch,
        )
    )

    await db.flush()


async def write_metric(
    db: AsyncSession,
    job_id: uuid.UUID,
    name: str,
    value: float,
    epoch: int | None = None,
    step: int | None = None,
):
    db.add(
        TrainingMetric(
            job_id=job_id,
            epoch=epoch,
            step=step,
            metric_name=name,
            metric_value=float(value),
        )
    )

    await db.flush()


async def register_worker() -> uuid.UUID:
    cpu_cores = os.cpu_count()
    memory_bytes = read_memory_bytes()
    now = utcnow()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkerNode).where(
                WorkerNode.name == settings.worker_name
            )
        )

        node = result.scalar_one_or_none()

        if node is None:
            node = WorkerNode(
                name=settings.worker_name,
                hostname=socket.gethostname(),
                platform=sys.platform,
                architecture=platform.machine() or None,
                cpu_cores=cpu_cores if cpu_cores and cpu_cores > 0 else None,
                memory_bytes=memory_bytes,
                status="online",
                capabilities=WORKER_CAPABILITIES,
                last_heartbeat_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(node)
        else:
            node.hostname = socket.gethostname()
            node.platform = sys.platform
            node.architecture = platform.machine() or None
            node.cpu_cores = (
                cpu_cores if cpu_cores and cpu_cores > 0 else None
            )
            node.memory_bytes = memory_bytes
            node.status = "online"
            node.capabilities = WORKER_CAPABILITIES
            node.last_heartbeat_at = now
            node.updated_at = now

        await db.commit()
        await db.refresh(node)

        logger.info(
            "Registered worker node %s (%s)",
            node.id,
            settings.worker_name,
        )

        return node.id


async def heartbeat_loop(worker_id: uuid.UUID):
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorkerNode)
                    .where(WorkerNode.id == worker_id)
                    .with_for_update()
                )
                node = result.scalar_one_or_none()

                if node is not None:
                    node.last_heartbeat_at = utcnow()
                    node.updated_at = utcnow()

                    if node.status == "offline":
                        node.status = "online"

                    await db.commit()
        except Exception:
            logger.exception("Worker heartbeat failed")

        await asyncio.sleep(settings.worker_heartbeat_interval)


async def set_worker_idle(worker_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkerNode)
            .where(WorkerNode.id == worker_id)
            .with_for_update()
        )
        node = result.scalar_one_or_none()

        if node is None:
            await db.rollback()
            return

        if node.status == "busy":
            node.status = "online"
            node.updated_at = utcnow()

        await db.commit()


async def set_worker_offline(worker_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkerNode)
            .where(WorkerNode.id == worker_id)
            .with_for_update()
        )
        node = result.scalar_one_or_none()

        if node is None:
            await db.rollback()
            return

        node.status = "offline"
        node.updated_at = utcnow()
        await db.commit()


async def claim_job(worker_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        worker_result = await db.execute(
            select(WorkerNode)
            .where(WorkerNode.id == worker_id)
            .with_for_update()
        )
        worker = worker_result.scalar_one_or_none()

        if worker is None or worker.status == "maintenance":
            await db.rollback()
            return None

        result = await db.execute(
            select(TrainingJob)
            .where(TrainingJob.status == "queued")
            .order_by(
                TrainingJob.queued_at.asc()
            )
            .limit(1)
            .with_for_update(
                skip_locked=True
            )
        )

        job = result.scalar_one_or_none()

        if job is None:
            await db.rollback()
            return None

        transition_or_raise(job.status, "preparing")
        job.status = "preparing"
        job.worker_node_id = worker_id
        job.started_at = utcnow()
        job.progress_percent = 5
        job.updated_at = utcnow()

        worker.status = "busy"
        worker.last_heartbeat_at = utcnow()
        worker.updated_at = utcnow()

        await db.commit()

        return job.id


async def is_job_cancelled(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(TrainingJob.status).where(
            TrainingJob.id == job_id
        )
    )
    current_status = result.scalar_one_or_none()
    return current_status == "cancelled"


async def ensure_not_cancelled(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> bool:
    if await is_job_cancelled(db, job_id):
        logger.info(
            "Job %s was cancelled",
            job_id,
        )
        return False

    return True


async def run_job(job_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TrainingJob).where(
                TrainingJob.id == job_id
            )
        )

        job = result.scalar_one()

        try:
            template_result = await db.execute(
                select(TrainingTemplateVersion).where(
                    TrainingTemplateVersion.id
                    == job.template_version_id
                )
            )

            template_version = (
                template_result.scalar_one()
            )

            dataset_version_result = await db.execute(
                select(DatasetVersion).where(
                    DatasetVersion.id
                    == job.dataset_version_id
                )
            )

            dataset_version = (
                dataset_version_result.scalar_one()
            )

            dataset_result = await db.execute(
                select(Dataset).where(
                    Dataset.id
                    == dataset_version.dataset_id
                )
            )

            dataset = dataset_result.scalar_one()

            await write_log(
                db,
                job.id,
                (
                    f"Preparing job using template "
                    f"'{template_version.entrypoint}'"
                ),
            )

            await db.commit()

            if not await ensure_not_cancelled(db, job.id):
                return

            if dataset.framework != "sklearn":
                raise ValueError(
                    "Current worker supports only sklearn datasets"
                )

            sklearn_name = (
                dataset.metadata_.get("sklearn_name")
                if dataset.metadata_
                else None
            )

            if not sklearn_name:
                sklearn_name = (
                    dataset_version.metadata_.get(
                        "sklearn_name"
                    )
                    if dataset_version.metadata_
                    else None
                )

            if not sklearn_name:
                raise ValueError(
                    "Dataset does not contain sklearn_name metadata"
                )

            X, y = load_builtin_dataset(
                sklearn_name
            )

            params = dict(job.parameters or {})

            test_size = float(
                params.get("test_size", 0.2)
            )

            random_state = int(
                params.get("random_state", 42)
            )

            model_name = str(
                params.get("model", "random_forest")
            )

            transition_or_raise(job.status, "running")
            job.status = "running"
            job.progress_percent = 20
            job.updated_at = utcnow()

            await write_log(
                db,
                job.id,
                (
                    f"Dataset loaded: "
                    f"{X.shape[0]} samples, "
                    f"{X.shape[1]} features"
                ),
            )

            await db.commit()

            stratify = y if "classification" in template_version.entrypoint else None

            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=test_size,
                random_state=random_state,
                stratify=stratify,
            )

            if "classification" in template_version.entrypoint:
                model = create_classification_model(
                    model_name,
                    params,
                )
            elif "regression" in template_version.entrypoint:
                model = create_regression_model(
                    model_name,
                    params,
                )
            else:
                raise ValueError(
                    f"Unsupported template entrypoint: "
                    f"{template_version.entrypoint}"
                )

            await write_log(
                db,
                job.id,
                f"Training model: {model_name}",
            )

            job.progress_percent = 40
            job.updated_at = utcnow()

            await db.commit()

            if not await ensure_not_cancelled(db, job.id):
                return

            await asyncio.to_thread(
                model.fit,
                X_train,
                y_train,
            )

            job.progress_percent = 70
            job.updated_at = utcnow()

            await write_log(
                db,
                job.id,
                "Model training completed",
            )

            await db.commit()

            if not await ensure_not_cancelled(db, job.id):
                return

            transition_or_raise(job.status, "evaluating")
            job.status = "evaluating"
            job.progress_percent = 80
            job.updated_at = utcnow()

            await write_log(
                db,
                job.id,
                "Evaluating model",
            )

            await db.commit()

            predictions = await asyncio.to_thread(
                model.predict,
                X_test,
            )

            metrics = {}

            if "classification" in template_version.entrypoint:
                accuracy = accuracy_score(
                    y_test,
                    predictions,
                )

                f1 = f1_score(
                    y_test,
                    predictions,
                    average="weighted",
                )

                metrics = {
                    "accuracy": float(accuracy),
                    "f1": float(f1),
                }

            else:
                mse = mean_squared_error(
                    y_test,
                    predictions,
                )

                mae = mean_absolute_error(
                    y_test,
                    predictions,
                )

                r2 = r2_score(
                    y_test,
                    predictions,
                )

                metrics = {
                    "mse": float(mse),
                    "mae": float(mae),
                    "r2": float(r2),
                }

            for metric_name, metric_value in metrics.items():
                await write_metric(
                    db,
                    job.id,
                    metric_name,
                    metric_value,
                )

            job.metrics_summary = metrics
            job.progress_percent = 90
            job.updated_at = utcnow()

            await db.commit()

            if not await ensure_not_cancelled(db, job.id):
                return

            transition_or_raise(job.status, "exporting")
            job.status = "exporting"
            job.updated_at = utcnow()

            await write_log(
                db,
                job.id,
                "Exporting model artifact",
            )

            await db.commit()

            artifact_root = settings.artifact_root
            artifact_path = artifact_root / f"{job.id}.joblib"

            size_bytes, checksum = await asyncio.to_thread(
                export_joblib_artifact,
                model,
                artifact_path,
            )

            final_result = await db.execute(
                select(TrainingJob)
                .where(TrainingJob.id == job.id)
                .with_for_update()
            )
            final_job = final_result.scalar_one()

            if final_job.status == "cancelled":
                await db.rollback()

                try:
                    artifact_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove cancelled artifact %s",
                        artifact_path,
                    )

                logger.info(
                    "Job %s was cancelled before completion",
                    job.id,
                )
                return

            transition_or_raise(final_job.status, "completed")

            artifact = ModelArtifact(
                job_id=final_job.id,
                owner_user_id=final_job.owner_user_id,
                name=(
                    final_job.name
                    or f"job-{final_job.id}"
                ),
                version=1,
                format="joblib",
                storage_uri=str(artifact_path.resolve()),
                checksum_sha256=checksum,
                size_bytes=size_bytes,
                metrics_=metrics,
                metadata_={
                    "framework": "sklearn",
                    "template_entrypoint":
                        template_version.entrypoint,
                    "dataset": sklearn_name,
                },
            )

            db.add(artifact)

            final_job.status = "completed"
            final_job.progress_percent = 100
            final_job.finished_at = utcnow()
            final_job.updated_at = utcnow()

            await write_log(
                db,
                final_job.id,
                (
                    "Training job completed "
                    "successfully"
                ),
            )

            await db.commit()

            logger.info(
                "Job %s completed",
                final_job.id,
            )

        except Exception as exc:
            logger.exception(
                "Job %s failed",
                job.id,
            )

            await db.rollback()

            result = await db.execute(
                select(TrainingJob)
                .where(TrainingJob.id == job_id)
                .with_for_update()
            )

            failed_job = result.scalar_one()

            if failed_job.status == "cancelled":
                logger.info(
                    "Job %s was cancelled; preserving cancelled state",
                    job.id,
                )
                await db.rollback()
                return

            try:
                transition_or_raise(
                    failed_job.status,
                    "failed",
                )
            except JobStateError:
                await db.rollback()
                return

            failed_job.status = "failed"
            failed_job.error_code = type(
                exc
            ).__name__
            failed_job.error_message = str(exc)
            failed_job.finished_at = utcnow()
            failed_job.updated_at = utcnow()

            db.add(
                TrainingLog(
                    job_id=job_id,
                    level="ERROR",
                    message=str(exc),
                )
            )

            await db.commit()


async def worker_loop(worker_id: uuid.UUID):
    logger.info("ML worker started")

    while True:
        try:
            job_id = await claim_job(worker_id)

            if job_id is not None:
                logger.info(
                    "Claimed job %s",
                    job_id,
                )

                try:
                    await run_job(job_id)
                finally:
                    await set_worker_idle(worker_id)

            else:
                await asyncio.sleep(
                    settings.worker_poll_interval
                )

        except Exception:
            logger.exception(
                "Worker loop error"
            )
            await asyncio.sleep(
                settings.worker_poll_interval
            )


async def main():
    worker_id = await register_worker()
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(worker_id)
    )

    try:
        await worker_loop(worker_id)
    finally:
        heartbeat_task.cancel()

        with suppress(asyncio.CancelledError):
            await heartbeat_task

        await set_worker_offline(worker_id)
        logger.info("Worker node marked offline")


if __name__ == "__main__":
    asyncio.run(main())
