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
from app.services.image_pipeline import compose_main_image
from app.templates import TEMPLATES, get_template

router = APIRouter(prefix="/api")


def _public_url(path: Path) -> str:
    settings = get_settings()
    return f"{settings.public_base_url}/{path.as_posix()}"


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


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ProductShot AI Backend"}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates() -> list[TemplateOut]:
    return list(TEMPLATES.values())


@router.post("/upload", response_model=SourceImageOut)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)) -> SourceImage:
    settings = get_settings()
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPG, PNG and WebP images are supported")

    suffix = Path(file.filename or "image.png").suffix.lower() or ".png"
    image_id = str(uuid4())
    relative_path = Path("storage/uploads") / f"{image_id}{suffix}"
    absolute_path = Path(relative_path)
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
        original_filename=file.filename or f"{image_id}{suffix}",
        file_path=str(relative_path),
        public_url=_public_url(relative_path),
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

    fmt = request.output_format.lower().replace("jpeg", "jpg")
    width = request.width or template.width
    height = request.height or template.height
    relative_output = Path("storage/outputs") / f"{task_id}-{template.id}-{width}x{height}.{fmt}"

    try:
        output_path, report = compose_main_image(source.file_path, request, relative_output)
        asset = GeneratedAsset(
            id=str(uuid4()),
            task_id=task.id,
            output_type=template.id,
            file_path=str(output_path),
            public_url=_public_url(output_path),
            width=width,
            height=height,
            compliance_json=json.dumps(report.to_dict(), ensure_ascii=False),
        )
        task.status = "success"
        task.compliance_score = report.score
        db.add(asset)
        db.add(task)
        db.commit()
    except Exception as exc:
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
