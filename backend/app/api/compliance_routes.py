from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from PIL import UnidentifiedImageError
from sqlalchemy.orm import Session

from app.auth import create_resource_signature, get_current_user, verify_resource_signature
from app.config import get_settings
from app.database import get_db
from app.models import ComplianceAnalysis, SourceImage, User
from app.schemas import ComplianceAnalysisOut, ComplianceAnalyzeRequest, ComplianceContextOut, SegmentationOut
from app.services.precheck import analyze_source_image


router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _signed_mask_url(analysis_id: str) -> str:
    settings = get_settings()
    expires, signature = create_resource_signature("compliance-mask", analysis_id)
    return f"{settings.public_base_url.rstrip('/')}/api/compliance/analyses/{analysis_id}/mask?expires={expires}&sig={signature}"


def _safe_mask_response(file_path: str | Path) -> FileResponse:
    settings = get_settings()
    storage_root = settings.storage_path.resolve()
    resolved_path = Path(file_path).resolve()
    try:
        resolved_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Mask 不存在") from exc
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Mask 不存在")
    return FileResponse(resolved_path, media_type="image/png")


def _load_json(raw: str, fallback):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _analysis_to_out(analysis: ComplianceAnalysis) -> ComplianceAnalysisOut:
    segmentation_data = _load_json(analysis.segmentation_json, {})
    segmentation_data["mask_url"] = _signed_mask_url(analysis.id) if analysis.mask_path else None
    return ComplianceAnalysisOut(
        id=analysis.id,
        source_image_id=analysis.source_image_id,
        context=ComplianceContextOut(
            platform=analysis.platform,
            marketplace=analysis.marketplace,
            image_role=analysis.image_role,
            category=analysis.category,
            rule_set_version=analysis.rule_set_version,
        ),
        status=analysis.status,
        score=analysis.score,
        segmentation=SegmentationOut(**segmentation_data),
        metrics=_load_json(analysis.metrics_json, {}),
        issues=_load_json(analysis.issues_json, []),
        fix_plan=_load_json(analysis.fix_plan_json, []),
        created_at=analysis.created_at,
    )


@router.post("/analyze", response_model=ComplianceAnalysisOut)
def analyze_compliance(
    payload: ComplianceAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComplianceAnalysisOut:
    source = (
        db.query(SourceImage)
        .filter(SourceImage.id == payload.source_image_id, SourceImage.user_id == current_user.id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="原图不存在，请重新上传商品图")

    try:
        result = analyze_source_image(
            source.file_path,
            platform=payload.platform,
            marketplace=payload.marketplace,
            image_role=payload.image_role,
            category=payload.category,
        )
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="图片无法读取，请重新上传后再检测") from exc

    analysis_id = str(uuid4())
    settings = get_settings()
    mask_path: Path | None = None
    if result.segmentation.mask is not None:
        mask_path = settings.storage_path / "masks" / f"{analysis_id}.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        result.segmentation.mask.save(mask_path, format="PNG", optimize=True)

    segmentation_payload = {
        "status": result.segmentation.status,
        "confidence": result.segmentation.confidence,
        "bbox": list(result.segmentation.bbox) if result.segmentation.bbox else None,
        "foreground_area_ratio": result.segmentation.foreground_area_ratio,
        "touches_edge": result.segmentation.touches_edge,
        "rectangularity": result.segmentation.rectangularity,
        "source": result.segmentation.source,
        "warnings": result.segmentation.warnings,
    }
    analysis = ComplianceAnalysis(
        id=analysis_id,
        user_id=current_user.id,
        source_image_id=source.id,
        platform=payload.platform,
        marketplace=payload.marketplace,
        image_role=payload.image_role,
        category=payload.category,
        rule_set_version=result.rule_set_version,
        status=result.status,
        score=result.score,
        segmentation_status=result.segmentation.status,
        segmentation_confidence=result.segmentation.confidence,
        segmentation_json=json.dumps(segmentation_payload, ensure_ascii=False),
        mask_path=str(mask_path) if mask_path else None,
        metrics_json=json.dumps(result.metrics, ensure_ascii=False),
        issues_json=json.dumps(result.issues, ensure_ascii=False),
        fix_plan_json=json.dumps(result.fix_plan, ensure_ascii=False),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return _analysis_to_out(analysis)


@router.get("/analyses/{analysis_id}", response_model=ComplianceAnalysisOut)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComplianceAnalysisOut:
    analysis = (
        db.query(ComplianceAnalysis)
        .filter(ComplianceAnalysis.id == analysis_id, ComplianceAnalysis.user_id == current_user.id)
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="检测报告不存在")
    return _analysis_to_out(analysis)


@router.get("/analyses/{analysis_id}/mask")
def view_analysis_mask(
    analysis_id: str,
    expires: int,
    sig: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    verify_resource_signature("compliance-mask", analysis_id, expires, sig)
    analysis = db.get(ComplianceAnalysis, analysis_id)
    if analysis is None or not analysis.mask_path:
        raise HTTPException(status_code=404, detail="Mask 不存在")
    return _safe_mask_response(analysis.mask_path)
