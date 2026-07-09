from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, selectinload
from PIL import Image, ImageOps, UnidentifiedImageError

from app.auth import check_login_rate_limit, clear_login_attempts, create_access_token, create_resource_signature, get_current_user, hash_password, normalize_email, record_failed_login, verify_password, verify_resource_signature
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import GeneratedAsset, GenerationTask, SourceImage, User
from app.schemas import AssetOut, AuthLoginRequest, AuthRegisterRequest, AuthTokenOut, ComplianceReport, GenerateRequest, HistoryOut, SourceImageOut, TaskOut, TemplateOut, UserOut
from app.services.image_pipeline import compose_subject_image, prepare_subject
from app.templates import TEMPLATES, get_template

router = APIRouter(prefix="/api")

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

FRIENDLY_GENERATION_FALLBACK = "生成失败，请换一张更清晰、主体更完整、背景更干净的商品图后重试。"
STEP_CREATED = "已创建任务，等待生成"
STEP_LOADING = "正在读取原图"
STEP_PREPARING = "正在抠图和增强"
STEP_COMPOSING = "正在合成主图结果"
STEP_FINISHED = "生成完成"
STEP_FAILED = "生成失败"


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


def _signed_resource_url(kind: str, resource_id: str, route_path: str) -> str:
    settings = get_settings()
    expires, signature = create_resource_signature(kind, resource_id)
    return f"{settings.public_base_url.rstrip('/')}{route_path}?expires={expires}&sig={signature}"


def _signed_source_image_url(image_id: str) -> str:
    return _signed_resource_url("source-image", image_id, f"/api/source-images/{image_id}/view")


def _signed_asset_url(asset_id: str) -> str:
    return _signed_resource_url("asset", asset_id, f"/api/assets/{asset_id}/view")


def _safe_file_response(file_path: str | Path) -> FileResponse:
    settings = get_settings()
    storage_root = settings.storage_path.resolve()
    resolved_path = Path(file_path).resolve()
    try:
        resolved_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(resolved_path)


def _safe_download_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip(".-_")
    return normalized or "asset"


def _zip_asset_name(asset: GeneratedAsset, index: int) -> str:
    suffix = Path(asset.file_path).suffix.lower() or ".png"
    output_type = _safe_download_name(asset.output_type)
    return f"{index:02d}-{output_type}-{asset.width}x{asset.height}{suffix}"


def _friendly_generation_error(exc: Exception) -> str:
    if isinstance(exc, UnidentifiedImageError):
        return "图片无法读取，请确认文件未损坏，并重新上传 JPG、PNG 或 WebP 图片。"
    if isinstance(exc, FileNotFoundError):
        return "原图文件不存在，请重新上传商品图后再生成。"
    if isinstance(exc, PermissionError):
        return "图片保存失败，服务端没有写入权限，请检查 storage 目录权限。"
    if isinstance(exc, MemoryError):
        return "图片过大或处理占用内存过高，请压缩图片后重试。"

    raw_message = str(exc).strip()
    message = raw_message.lower()
    if "cannot identify image file" in message or "unidentified" in message:
        return "图片无法读取，请确认文件未损坏，并重新上传 JPG、PNG 或 WebP 图片。"
    if "no such file" in message or "not found" in message:
        return "原图文件不存在，请重新上传商品图后再生成。"
    if "permission denied" in message:
        return "图片保存失败，服务端没有写入权限，请检查 storage 目录权限。"
    if "not enough memory" in message or "memory" in message:
        return "图片过大或处理占用内存过高，请压缩图片后重试。"
    if "output_format" in message or "unsupported format" in message or "unknown file extension" in message:
        return "输出格式不支持，请选择 PNG、JPG 或 WebP 后重试。"
    if "width" in message or "height" in message or "tile cannot extend outside image" in message:
        return "图片尺寸或导出尺寸不符合要求，请使用更清晰的商品图，并保持导出尺寸在 512 到 4096 像素之间。"
    if "background" in message or "color" in message or "hex" in message:
        return "背景颜色参数不正确，请选择纯白、透明、浅灰或有效的自定义颜色。"
    if raw_message and not any(token in raw_message for token in ["Traceback", "File \"", "app/", "site-packages", "PIL."]):
        return raw_message
    return FRIENDLY_GENERATION_FALLBACK


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_to_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def _auth_token_for_user(user: User) -> AuthTokenOut:
    return AuthTokenOut(access_token=create_access_token(user.id), user=_user_to_out(user))


def _source_image_to_out(source: SourceImage) -> SourceImageOut:
    return SourceImageOut(
        id=source.id,
        original_filename=source.original_filename,
        public_url=_signed_source_image_url(source.id),
        width=source.width,
        height=source.height,
        content_type=source.content_type,
        created_at=source.created_at,
    )


def _asset_to_out(asset: GeneratedAsset) -> AssetOut:
    compliance = None
    if asset.compliance_json:
        compliance = ComplianceReport(**json.loads(asset.compliance_json))
    return AssetOut(
        id=asset.id,
        output_type=asset.output_type,
        public_url=_signed_asset_url(asset.id),
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
        progress=task.progress or 0,
        current_step=task.current_step,
        error_message=task.error_message,
        compliance_score=task.compliance_score,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assets=[_asset_to_out(asset) for asset in task.assets],
    )


def _task_for_user(db: Session, task_id: str, user_id: str) -> GenerationTask | None:
    return db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task_id, GenerationTask.user_id == user_id).first()


def _set_task_progress(db: Session, task: GenerationTask, *, status: str | None = None, progress: int | None = None, current_step: str | None = None) -> None:
    if status is not None:
        task.status = status
    if progress is not None:
        task.progress = min(max(progress, 0), 100)
    if current_step is not None:
        task.current_step = current_step
    db.add(task)
    db.commit()


def _create_generation_task(db: Session, request: GenerateRequest, template_id: str, user_id: str) -> GenerationTask:
    task = GenerationTask(id=str(uuid4()), user_id=user_id, source_image_id=request.source_image_id, template_id=template_id, status="queued", progress=0, current_step=STEP_CREATED, request_json=request.model_dump_json())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _variant_requests(request: GenerateRequest, width: int, height: int) -> list[tuple[str, GenerateRequest]]:
    template = get_template(request.template_id)
    base_background = request.background or template.background
    base_shadow = template.shadow_enabled if request.add_shadow is None else request.add_shadow
    base_format = request.output_format.lower().replace("jpeg", "jpg")
    variants: list[tuple[str, GenerateRequest]] = [
        (request.template_id, request.model_copy(update={"width": width, "height": height, "background": base_background, "add_shadow": base_shadow, "output_format": base_format})),
        ("transparent-png", request.model_copy(update={"template_id": "transparent-png", "width": width, "height": height, "background": "transparent", "add_shadow": False, "output_format": "png"})),
        ("soft-shadow-packshot", request.model_copy(update={"template_id": "soft-shadow-packshot", "width": width, "height": height, "background": "white", "add_shadow": True, "output_format": "png"})),
        ("hd-2000px", request.model_copy(update={"width": max(width, 2000), "height": max(height, 2000), "background": "transparent" if base_background == "transparent" else "white", "add_shadow": base_shadow and base_background != "transparent", "output_format": "png"})),
    ]
    deduped: list[tuple[str, GenerateRequest]] = []
    seen: set[tuple] = set()
    for output_type, variant in variants:
        key = (variant.template_id, variant.width, variant.height, variant.product_fill_ratio, variant.background, variant.add_shadow, variant.output_format)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((output_type, variant))
    return deduped


def _run_generation_task(task_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    created_paths: list[Path] = []
    try:
        task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if task is None or task.status not in {"queued", "processing"}:
            return
        _set_task_progress(db, task, status="processing", progress=8, current_step=STEP_LOADING)
        request = GenerateRequest.model_validate_json(task.request_json)
        source = db.get(SourceImage, task.source_image_id)
        if source is None:
            raise FileNotFoundError("source image not found")
        template = get_template(request.template_id)
        width = request.width or template.width
        height = request.height or template.height
        _set_task_progress(db, task, status="processing", progress=20, current_step=STEP_PREPARING)
        subject = prepare_subject(source.file_path, edge_repair=request.edge_repair, auto_enhance=request.auto_enhance, sharpen=request.sharpen)
        primary_score: float | None = None
        variants = _variant_requests(request, width, height)
        total_variants = max(len(variants), 1)
        for index, (output_type, variant_request) in enumerate(variants, start=1):
            progress = 35 + int((index - 1) / total_variants * 50)
            _set_task_progress(db, task, status="processing", progress=progress, current_step=f"{STEP_COMPOSING}（{index}/{total_variants}）")
            fmt = variant_request.output_format.lower().replace("jpeg", "jpg")
            variant_width = variant_request.width or width
            variant_height = variant_request.height or height
            output_path = settings.storage_path / "outputs" / f"{task_id}-{output_type}-{variant_width}x{variant_height}.{fmt}"
            created_paths.append(output_path)
            saved_path, report = compose_subject_image(subject, variant_request, output_path)
            asset_id = str(uuid4())
            asset = GeneratedAsset(id=asset_id, task_id=task.id, output_type=output_type, file_path=str(saved_path), public_url=_signed_asset_url(asset_id), width=variant_width, height=variant_height, compliance_json=json.dumps(report.to_dict(), ensure_ascii=False))
            if primary_score is None:
                primary_score = report.score
            db.add(asset)
            db.commit()
        task.status = "success"
        task.progress = 100
        task.current_step = STEP_FINISHED
        task.compliance_score = primary_score
        task.error_message = None
        db.add(task)
        db.commit()
    except Exception as exc:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        failed_task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if failed_task is not None:
            failed_task.status = "failed"
            failed_task.progress = max(failed_task.progress or 0, 1)
            failed_task.current_step = STEP_FAILED
            failed_task.error_message = _friendly_generation_error(exc)
            db.add(failed_task)
            db.commit()
    finally:
        db.close()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ProductShot AI Backend"}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates() -> list[TemplateOut]:
    return list(TEMPLATES.values())


@router.get("/source-images/{image_id}/view")
def view_source_image(image_id: str, expires: int, sig: str, db: Session = Depends(get_db)) -> FileResponse:
    verify_resource_signature("source-image", image_id, expires, sig)
    source = db.get(SourceImage, image_id)
    if source is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return _safe_file_response(source.file_path)


@router.get("/assets/{asset_id}/view")
def view_asset(asset_id: str, expires: int, sig: str, db: Session = Depends(get_db)) -> FileResponse:
    verify_resource_signature("asset", asset_id, expires, sig)
    asset = db.get(GeneratedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return _safe_file_response(asset.file_path)


@router.post("/auth/register", response_model=AuthTokenOut)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenOut:
    email = normalize_email(payload.email)
    exists = db.query(User).filter(User.email == email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    user = User(id=str(uuid4()), email=email, password_hash=hash_password(payload.password), display_name=(payload.display_name or email.split("@", 1)[0]).strip()[:120])
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_token_for_user(user)


@router.post("/auth/login", response_model=AuthTokenOut)
def login(payload: AuthLoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthTokenOut:
    email = normalize_email(payload.email)
    client_ip = _client_ip(request)
    check_login_rate_limit(email, client_ip)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        record_failed_login(email, client_ip)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user.is_active:
        record_failed_login(email, client_ip)
        raise HTTPException(status_code=403, detail="账号已停用")
    clear_login_attempts(email, client_ip)
    return _auth_token_for_user(user)


@router.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return _user_to_out(current_user)


@router.post("/upload", response_model=SourceImageOut)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> SourceImageOut:
    settings = get_settings()
    allowed_types = set(CONTENT_TYPE_EXTENSIONS)
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG 和 WebP 格式的商品图片")
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
                raise HTTPException(status_code=413, detail=f"图片过大，最大支持 {settings.max_upload_mb}MB")
            buffer.write(chunk)
    try:
        with Image.open(absolute_path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
    except Exception as exc:
        absolute_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="图片无法读取，请确认文件未损坏后重新上传") from exc
    source = SourceImage(id=image_id, user_id=current_user.id, original_filename=Path(file.filename or f"{image_id}{suffix}").name, file_path=str(absolute_path), public_url=_signed_source_image_url(image_id), width=width, height=height, content_type=file.content_type or "application/octet-stream")
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_image_to_out(source)


@router.post("/generate", response_model=TaskOut)
def generate_image(request: GenerateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> TaskOut:
    source = db.query(SourceImage).filter(SourceImage.id == request.source_image_id, SourceImage.user_id == current_user.id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="原图不存在，请重新上传商品图")
    try:
        template = get_template(request.template_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="模板不存在，请重新选择模板") from exc
    task = _create_generation_task(db, request, template.id, current_user.id)
    background_tasks.add_task(_run_generation_task, task.id)
    task = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task.id).one()
    return _task_to_out(task)


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> TaskOut:
    original_task = _task_for_user(db, task_id, current_user.id)
    if original_task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if original_task.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败任务可以重试")
    try:
        request = GenerateRequest.model_validate_json(original_task.request_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="原任务参数无法读取，请重新上传图片后生成") from exc
    source = db.query(SourceImage).filter(SourceImage.id == request.source_image_id, SourceImage.user_id == current_user.id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="原图不存在，请重新上传商品图")
    try:
        template = get_template(request.template_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="模板不存在，请重新选择模板") from exc
    task = _create_generation_task(db, request, template.id, current_user.id)
    background_tasks.add_task(_run_generation_task, task.id)
    task = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.id == task.id).one()
    return _task_to_out(task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> TaskOut:
    task = _task_for_user(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_to_out(task)


@router.get("/tasks/{task_id}/download.zip")
def download_task_assets(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> StreamingResponse:
    task = _task_for_user(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.assets:
        raise HTTPException(status_code=404, detail="当前任务没有可下载的生成结果")
    existing_assets: list[GeneratedAsset] = []
    missing_assets: list[str] = []
    for asset in task.assets:
        if Path(asset.file_path).exists():
            existing_assets.append(asset)
        else:
            missing_assets.append(asset.output_type)
    if not existing_assets:
        raise HTTPException(status_code=404, detail="生成图片文件缺失，无法下载")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, asset in enumerate(existing_assets, start=1):
            archive.write(asset.file_path, arcname=_zip_asset_name(asset, index))
        if missing_assets:
            archive.writestr("README.txt", "Some generated files were missing and were not included:\n" + "\n".join(f"- {name}" for name in missing_assets))
    buffer.seek(0)
    filename = f"productshot-{_safe_download_name(task.id)}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@router.get("/history", response_model=HistoryOut)
def history(limit: int = 30, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> HistoryOut:
    limit = min(max(limit, 1), 100)
    tasks = db.query(GenerationTask).options(selectinload(GenerationTask.assets)).filter(GenerationTask.user_id == current_user.id).order_by(GenerationTask.created_at.desc()).limit(limit).all()
    return HistoryOut(tasks=[_task_to_out(task) for task in tasks])


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    task = _task_for_user(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    for asset in task.assets:
        Path(asset.file_path).unlink(missing_ok=True)
        db.delete(asset)
    db.delete(task)
    db.commit()
    return {"ok": True}
