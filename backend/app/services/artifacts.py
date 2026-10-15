from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import settings


def resolve_stored_artifact_path(storage_uri: str) -> Path | None:
    root = settings.artifact_root.resolve()

    try:
        path = Path(storage_uri).resolve()
    except OSError:
        return None

    if not path.is_relative_to(root):
        return None

    if not path.is_file():
        return None

    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def artifact_download_filename(job_id, output_format: str) -> str:
    extension = output_format if output_format in {"joblib", "onnx", "pth"} else "bin"
    return f"{job_id}.{extension}"
