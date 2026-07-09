from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload
from PIL import Image, ImageOps

from app.config import get_settings
from app.database import get_db
from app.models import GeneratedAsset, GenerationTask, SourceImage
from app.schemas import AssetOut, ComplianceReport, GenerateRequest, HistoryOut, SourceImageOut, TaskOut, TemplateOut
from app.services.image_pipeline import compose_subject_image, prepare_subject
from app.templates import TEMPLATES, get_template

router = APIRouter(prefix="/api")

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _safe_extension(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return CONTENT_TYPE_EXTENSIONS.get(file.content_type or "", ".png")


def _storage_public_url(path: Path) -> str:
    settings = get_settings()
    storage_root = settings.storage_path.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(storage_root)
    except ValueError:
        relative = Path(path.name)
    return f"{settings.public_base_url.rstrip('/')}/storage/{relative.as_posix()}"


def _asset_to_out(asset: GeneratedAsset) -> AssetOut:
    compliance = None
    if asset.compliance_json:
        compliance = ComplianceReport(**json.loads(asset.compliance_json))
    return AssetOut(
        id=asset.id,
        output_type=asset.output_type,
        public_url=asset.public_url,
        width=asset.width,
        height=asset.height,
        compliance=compliance,
        created_at=asset.created_at,
    )


def _task_to_out(task: GenerationTask) -> TaskOut:
    return TaskOut(
        id=task.id,
        source_image_id=task.source_image_id,
        template_id=task.template_id,
        status=task.status,
        error_message=task.error_message,
        compliance_score=task.compliance_score,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assets=[_asset_to_out(asset) for asset in task.assets],
    )


def _variant_requests(request: GenerateRequest, width: int, height: int) -> list[tuple[str, GenerateRequest]]:
    """Return the product outputs shown in the UI while avoiding duplicate renders."""
    template = get_template(request.template_id)
    base_background = request.background or template.background
    base_shadow = template.shadow_enabled if request.add_shadow is None else request.add_shadow
    base_format = request.output_format.lower().replace("jpeg", "jpg")

    variants: list[tuple[str, GenerateRequest]] = [
        (
            request.template_id,
            request.model_copy(
                update={
                    "width": width,
                    "height": height,
                    "background": base_background,
                    "add_shadow": base_shadow,
                    "output_format": base_format,
                }
            ),
        ),
        (
            "transparent-png",
            request.model_copy(
                update={
                    "template_id": "transparent-png",
                    "width": width,
                    "height": height,
                    "background": "transparent",
                    "add_shadow": False,
                    "output_format": "png",
                }
            ),
        ),
        (
            "soft-shadow-packshot",
            request.model_copy(
                update={
                    "template_id": "soft-shadow-packshot",
                    "width": width,
                    "height": height,
                    "background": "white",
                    "add_shadow": True,
                    "output_format": "png",
                }
            ),
        ),
        (
            "hd-2000px",
            request.model_copy(
                update={
                    "width": max(width, 2000),
                    "height": max(height, 2000),
                    "background": "transparent" if base_background == "transparent" else "white",
                    "add_shadow": base_shadow and base_background != "transparent",
                    "output_format": "png",
                }
            ),
        ),
    ]

    deduped: list[tuple[str, GenerateRequest]] = []
    seen: set[tuple] = set()
    for output_type, variant in variants:
        key = (
            variant.template_id,
            variant.width,
            variant.height,
            variant.product_fill_ratio,
            variant.background,
            variant.add_shadow,
            variant.output_format,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append((output_type, variant))
    return deduped


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ProductShot AI Backend"}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates() -> list[TemplateOut]:
    return list(TEMPLATES.values())


@router.post("/upload", response_model=SourceImageOut)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)) -> SourceImage:
    settings = get_settings()
    allowed_types = set(CONTENT_TYPE_EXTENSIONS)
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPG, PNG and WebP images are supported")

    suffix = _safe_extension(file)
    image_id = str(uuid4())
    absolute_path = settings.storage_path / "uploads" / f"{image_id}{suffix}"
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    bytes_written = 0
    with absolute_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                absolute_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb}MB")
            buffer.write(chunk)

    try:
        with Image.open(absolute_path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
    except Exception as exc:
        absolute_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    source = SourceImage(
        id=image_id,
        original_filename=Path(file.filename or f"{image_id}{suffix}").name,
        file_path=str(absolute_path),
        public_url=_storage_public_url(absolute_path),
        width=width,
        height=height,
        content_type=file.content_type or "application/octet-stream",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.post("/generate", response_model=TaskOut)
def generate_image(request: GenerateRequest, db: Session = Depends(get_db)) -> TaskOut:
    settings = get_settings()
    source = db.get(SourceImage, request.source_image_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source image not found")
    try:
        template = get_template(request.template_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = str(uuid4())
    task = GenerationTask(
        id=task_id,
        source_image_id=source.id,
        template_id=template.id,
        status="processing",
        request_json=request.model_dump_json(),
    )
    db.add(task)
    db.commit()

    width = request.width or template.width
    height = request.height or template.height
    created_paths: list[Path] = []

    try:
        subject = prepare_subject(
            source.file_path,
            edge_repair=request.edge_repair,
            auto_enhance=request.auto_enhance,
        )
        primary_score: float | None = None
        for output_type, variant_request in _variant_requests(request, width, height):
            fmt = variant_request.output_format.lower().replace("jpeg", "jpg")
            variant_width = variant_request.width or width
            variant_height = variant_request.height or height
            output_path = settings.storage_path / "outputs" / f"{task_id}-{output_type}-{variant_width}x{variant_height}.{fmt}"
            created_paths.append(output_path)

            saved_path, report = compose_subject_image(subject, variant_request, output_path)
            asset = GeneratedAsset(
                id=str(uuid4()),
                task_id=task.id,
                output_type=output_type,
                file_path=str(saved_path),
                public_url=_storage_public_url(saved_path),
                width=variant_width,
                height=variant_height,
                compliance_json=json.dumps(report.to_dict(), ensure_ascii=False),
            )
            if primary_score is None:
                primary_score = report.score
            db.add(asset)

        task.status = "success"
        task.compliance_score = primary_score
        db.add(task)
        db.commit()
    except Exception as exc:
        for path in created_paths:
            path.unlink(missing_ok=True)
        task.status = "failed"
        task.error_message = str(exc)
        db.add(task)
        db.commit()

    task = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task_id).one()
    return _task_to_out(task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    task = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_out(task)


@router.get("/history", response_model=HistoryOut)
def history(limit: int = 30, db: Session = Depends(get_db)) -> HistoryOut:
    limit = min(max(limit, 1), 100)
    tasks = (
        db.query(GenerationTask)
        .options(selectinload(GenerationTask.assets))
        .order_by(GenerationTask.created_at.desc())
        .limit(limit)
        .all()
    )
    return HistoryOut(tasks=[_task_to_out(task) for task in tasks])


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    task = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    for asset in task.assets:
        Path(asset.file_path).unlink(missing_ok=True)
        db.delete(asset)
    db.delete(task)
    db.commit()
    return {"ok": True}
