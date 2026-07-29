from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = settings.upload_max_size_mb * 1024 * 1024


@router.post("/image")
async def upload_image(file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file.content_type}",
        )

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件过大，最大 {settings.upload_max_size_mb} MB",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = ".jpg"
    if file.content_type == "image/png":
        ext = ".png"
    elif file.content_type == "image/webp":
        ext = ".webp"
    elif file.content_type == "image/gif":
        ext = ".gif"

    filename = f"journal-{uuid.uuid4()}{ext}"
    filepath = upload_dir / filename
    filepath.write_bytes(content)

    base_url = settings.upload_base_url.rstrip("/")
    url = f"{base_url}/{filename}"

    return {"url": url, "filename": filename}
