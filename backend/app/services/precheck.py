from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


RemoveFunction = Callable[[bytes], bytes]


@dataclass
class SegmentationResult:
    status: str
    confidence: float
    mask: Image.Image | None
    bbox: tuple[int, int, int, int] | None
    foreground_area_ratio: float
    touches_edge: bool
    rectangularity: float
    source: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class PrecheckResult:
    status: str
    score: float
    rule_set_version: str
    segmentation: SegmentationResult
    metrics: dict[str, Any]
    issues: list[dict[str, Any]]
    fix_plan: list[dict[str, Any]]


_RULES: dict[str, dict[str, Any]] = {
    "amazon": {
        "rule_set_version": "amazon-main-precheck-2026.07.1",
        "min_width": 1000,
        "min_height": 1000,
        "fill_min": 0.75,
        "fill_max": 0.90,
        "white_background": True,
        "background_severity": "blocker",
    },
    "google-merchant": {
        "rule_set_version": "google-merchant-precheck-2026.07.1",
        "min_width": 500,
        "min_height": 500,
        "fill_min": 0.70,
        "fill_max": 0.92,
        "white_background": False,
        "background_severity": "quality",
    },
    "universal": {
        "rule_set_version": "universal-product-precheck-2026.07.1",
        "min_width": 1000,
        "min_height": 1000,
        "fill_min": 0.60,
        "fill_max": 0.92,
        "white_background": False,
        "background_severity": "quality",
    },
}


def _meaningful_alpha(image: Image.Image) -> bool:
    if image.mode != "RGBA":
        return False
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    total = max(image.width * image.height, 1)
    transparent = sum(histogram[:250]) / total
    visible = sum(histogram[16:]) / total
    return transparent >= 0.002 and visible >= 0.002


def _threshold_mask(alpha: Image.Image) -> Image.Image:
    return alpha.convert("L").point(lambda value: 255 if value > 16 else 0)


def _mask_metrics(mask: Image.Image) -> tuple[tuple[int, int, int, int] | None, float, bool, float]:
    binary = _threshold_mask(mask)
    bbox = binary.getbbox()
    if bbox is None:
        return None, 0.0, False, 0.0

    histogram = binary.histogram()
    foreground_pixels = histogram[255]
    total_pixels = max(binary.width * binary.height, 1)
    foreground_area_ratio = foreground_pixels / total_pixels

    x1, y1, x2, y2 = bbox
    bbox_area = max((x2 - x1) * (y2 - y1), 1)
    rectangularity = foreground_pixels / bbox_area
    touches_edge = x1 <= 0 or y1 <= 0 or x2 >= binary.width or y2 >= binary.height
    return bbox, foreground_area_ratio, touches_edge, rectangularity


def _confidence_for_mask(
    *,
    source: str,
    bbox: tuple[int, int, int, int] | None,
    image_size: tuple[int, int],
    foreground_area_ratio: float,
    touches_edge: bool,
    rectangularity: float,
) -> tuple[str, float, list[str]]:
    if bbox is None or foreground_area_ratio <= 0.001:
        return "failed", 0.0, ["未能识别稳定的商品主体。"]

    width, height = image_size
    x1, y1, x2, y2 = bbox
    bbox_area_ratio = ((x2 - x1) * (y2 - y1)) / max(width * height, 1)
    confidence = 0.98 if source == "alpha" else 0.90
    warnings: list[str] = []

    if foreground_area_ratio < 0.01:
        confidence -= 0.45
        warnings.append("识别到的主体面积过小。")
    if foreground_area_ratio > 0.94:
        confidence -= 0.45
        warnings.append("主体几乎覆盖整张图片，可能仍包含原始背景。")
    if bbox_area_ratio > 0.92 and rectangularity > 0.94:
        confidence -= 0.40
        warnings.append("主体轮廓接近完整矩形，疑似把整张原图当成商品主体。")
    if touches_edge:
        confidence -= 0.12
        warnings.append("主体接触画布边缘，需要确认是否存在裁切。")
    if (x2 - x1) / max(width, 1) < 0.05 or (y2 - y1) / max(height, 1) < 0.05:
        confidence -= 0.25
        warnings.append("主体在某一方向上过窄，分割结果可能不稳定。")

    confidence = round(max(0.0, min(confidence, 1.0)), 3)
    status = "success" if confidence >= 0.75 else "low_confidence"
    return status, confidence, warnings


def segment_subject(image: Image.Image, remove_fn: RemoveFunction | None = None) -> SegmentationResult:
    rgba = image.convert("RGBA")
    source = "alpha"

    if _meaningful_alpha(rgba):
        mask = _threshold_mask(rgba.getchannel("A"))
    else:
        source = "rembg"
        try:
            if remove_fn is None:
                from rembg import remove as remove_fn  # type: ignore
            buffer = io.BytesIO()
            rgba.save(buffer, format="PNG")
            output = remove_fn(buffer.getvalue())
            segmented = Image.open(io.BytesIO(output)).convert("RGBA")
            mask = _threshold_mask(segmented.getchannel("A"))
        except Exception:
            return SegmentationResult(
                status="failed",
                confidence=0.0,
                mask=None,
                bbox=None,
                foreground_area_ratio=0.0,
                touches_edge=False,
                rectangularity=0.0,
                source=source,
                warnings=["自动抠图失败，系统未将原始矩形图片当作合格主体继续处理。"],
            )

    bbox, area_ratio, touches_edge, rectangularity = _mask_metrics(mask)
    status, confidence, warnings = _confidence_for_mask(
        source=source,
        bbox=bbox,
        image_size=rgba.size,
        foreground_area_ratio=area_ratio,
        touches_edge=touches_edge,
        rectangularity=rectangularity,
    )
    return SegmentationResult(
        status=status,
        confidence=confidence,
        mask=mask if status != "failed" else None,
        bbox=bbox,
        foreground_area_ratio=round(area_ratio, 4),
        touches_edge=touches_edge,
        rectangularity=round(rectangularity, 4),
        source=source,
        warnings=warnings,
    )


def _subject_metrics(image: Image.Image, segmentation: SegmentationResult) -> dict[str, Any]:
    if segmentation.mask is None or segmentation.bbox is None:
        return {}

    width, height = image.size
    x1, y1, x2, y2 = segmentation.bbox
    subject_width = x2 - x1
    subject_height = y2 - y1
    center_x = x1 + subject_width / 2
    center_y = y1 + subject_height / 2

    return {
        "subject_bbox": [x1, y1, x2, y2],
        "bbox_width_ratio": round(subject_width / max(width, 1), 4),
        "bbox_height_ratio": round(subject_height / max(height, 1), 4),
        "bbox_area_ratio": round((subject_width * subject_height) / max(width * height, 1), 4),
        "mask_area_ratio": segmentation.foreground_area_ratio,
        "center_offset_x": round(abs(center_x - width / 2) / max(width, 1), 4),
        "center_offset_y": round(abs(center_y - height / 2) / max(height, 1), 4),
        "margin_left": round(x1 / max(width, 1), 4),
        "margin_right": round((width - x2) / max(width, 1), 4),
        "margin_top": round(y1 / max(height, 1), 4),
        "margin_bottom": round((height - y2) / max(height, 1), 4),
        "touches_edge": segmentation.touches_edge,
        "rectangularity": segmentation.rectangularity,
    }


def _background_metrics(image: Image.Image, segmentation: SegmentationResult) -> dict[str, Any]:
    if segmentation.mask is None:
        return {}

    rgb = image.convert("RGB")
    max_dimension = max(rgb.size)
    if max_dimension > 1024:
        scale = 1024 / max_dimension
        size = (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale)))
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
        mask = segmentation.mask.resize(size, Image.Resampling.NEAREST)
    else:
        mask = segmentation.mask.copy()

    padding = max(3, int(min(rgb.size) * 0.008))
    if padding % 2 == 0:
        padding += 1
    foreground = mask.filter(ImageFilter.MaxFilter(size=padding))
    background = ImageOps.invert(_threshold_mask(foreground))
    background_pixels = background.histogram()[255]
    if background_pixels <= 0:
        return {"background_pixel_count": 0, "white_pixel_ratio": 0.0}

    r, g, b = rgb.split()
    white_r = r.point(lambda value: 255 if value >= 248 else 0)
    white_g = g.point(lambda value: 255 if value >= 248 else 0)
    white_b = b.point(lambda value: 255 if value >= 248 else 0)
    white = ImageChops.multiply(ImageChops.multiply(white_r, white_g), white_b)
    white_background = ImageChops.multiply(white, background)
    white_pixels = white_background.histogram()[255]
    stats = ImageStat.Stat(rgb, background)

    return {
        "background_pixel_count": background_pixels,
        "white_pixel_ratio": round(white_pixels / background_pixels, 4),
        "background_rgb_mean": [round(value, 2) for value in stats.mean],
        "background_rgb_stddev": [round(value, 2) for value in stats.stddev],
    }


def _subject_sharpness(image: Image.Image, segmentation: SegmentationResult) -> float | None:
    if segmentation.bbox is None or segmentation.mask is None:
        return None
    roi = image.convert("L").crop(segmentation.bbox)
    mask = segmentation.mask.crop(segmentation.bbox)
    if roi.width < 4 or roi.height < 4:
        return None
    edges = roi.filter(ImageFilter.FIND_EDGES)
    return round(ImageStat.Stat(edges, mask).var[0], 2)


def _issue(
    issue_id: str,
    *,
    severity: str,
    status: str,
    title: str,
    description: str,
    confidence: float,
    metrics: dict[str, Any] | None = None,
    auto_fix: str | None = None,
    requires_confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "rule_id": issue_id,
        "severity": severity,
        "status": status,
        "title": title,
        "description": description,
        "confidence": round(max(0.0, min(confidence, 1.0)), 3),
        "metrics": metrics or {},
        "evidence": [],
        "auto_fix": auto_fix,
        "requires_confirmation": requires_confirmation,
    }


def _fix(issue: dict[str, Any], action: str, risk: str, *, selected: bool, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": f"fix-{issue['id']}",
        "issue_id": issue["id"],
        "action": action,
        "risk": risk,
        "selected_by_default": selected,
        "parameters": parameters or {},
        "requires_confirmation": risk != "safe",
    }


def analyze_source_image(
    source_path: str | Path,
    *,
    platform: str,
    marketplace: str | None,
    image_role: str,
    category: str,
    remove_fn: RemoveFunction | None = None,
) -> PrecheckResult:
    rule = _RULES.get(platform, _RULES["universal"])
    with Image.open(source_path) as opened:
        detected_format = opened.format or "unknown"
        exif_orientation = int(opened.getexif().get(274, 1) or 1)
        image = ImageOps.exif_transpose(opened).convert("RGBA")

    segmentation = segment_subject(image, remove_fn=remove_fn)
    metrics: dict[str, Any] = {
        "width": image.width,
        "height": image.height,
        "detected_format": detected_format,
        "exif_orientation": exif_orientation,
        "platform": platform,
        "marketplace": marketplace or "",
        "image_role": image_role,
        "category": category,
    }
    metrics.update(_subject_metrics(image, segmentation))
    metrics.update(_background_metrics(image, segmentation))
    sharpness = _subject_sharpness(image, segmentation)
    if sharpness is not None:
        metrics["subject_sharpness_score"] = sharpness

    issues: list[dict[str, Any]] = []
    fix_plan: list[dict[str, Any]] = []

    if segmentation.status == "failed":
        issues.append(
            _issue(
                "universal.segmentation.failed",
                severity="blocker",
                status="failed",
                title="无法稳定识别商品主体",
                description="自动抠图失败，背景和构图规则不会被误判为通过。",
                confidence=1.0,
                requires_confirmation=True,
            )
        )
    elif segmentation.status == "low_confidence":
        issues.append(
            _issue(
                "universal.segmentation.low-confidence",
                severity="warning",
                status="unknown",
                title="商品主体识别置信度较低",
                description="分割结果可能仍包含原始背景，请查看主体 Mask 后确认。",
                confidence=max(1.0 - segmentation.confidence, 0.5),
                requires_confirmation=True,
            )
        )

    size_ok = image.width >= rule["min_width"] and image.height >= rule["min_height"]
    if not size_ok:
        issue = _issue(
            "universal.file.min-dimensions",
            severity="warning",
            status="failed",
            title="原图尺寸偏小",
            description=f"当前尺寸为 {image.width}×{image.height}，建议至少 {rule['min_width']}×{rule['min_height']}。",
            confidence=1.0,
            metrics={"width": image.width, "height": image.height},
            auto_fix="export_size",
        )
        issues.append(issue)
        fix_plan.append(_fix(issue, "export_size", "safe", selected=True, parameters={"min_width": rule["min_width"], "min_height": rule["min_height"]}))

    if segmentation.mask is not None and segmentation.bbox is not None:
        confidence = segmentation.confidence
        center_ok = metrics["center_offset_x"] <= 0.05 and metrics["center_offset_y"] <= 0.06
        if not center_ok:
            issue = _issue(
                "main.subject.centered",
                severity="warning",
                status="failed" if segmentation.status == "success" else "unknown",
                title="商品主体没有居中",
                description="商品中心偏离画布中心，建议重新居中排版。",
                confidence=confidence,
                metrics={"center_offset_x": metrics["center_offset_x"], "center_offset_y": metrics["center_offset_y"]},
                auto_fix="center_subject",
                requires_confirmation=segmentation.status != "success",
            )
            issues.append(issue)
            fix_plan.append(_fix(issue, "center_subject", "safe" if segmentation.status == "success" else "review", selected=segmentation.status == "success"))

        fill_ratio = max(metrics["bbox_width_ratio"], metrics["bbox_height_ratio"])
        if not rule["fill_min"] <= fill_ratio <= rule["fill_max"]:
            issue = _issue(
                "main.subject.dimension-ratio",
                severity="warning",
                status="failed" if segmentation.status == "success" else "unknown",
                title="商品占比不在推荐范围",
                description=f"当前最长边占比约 {round(fill_ratio * 100)}%，建议控制在 {round(rule['fill_min'] * 100)}%–{round(rule['fill_max'] * 100)}%。",
                confidence=confidence,
                metrics={"fill_ratio": round(fill_ratio, 4)},
                auto_fix="resize_subject",
                requires_confirmation=segmentation.status != "success",
            )
            issues.append(issue)
            fix_plan.append(_fix(issue, "resize_subject", "safe" if segmentation.status == "success" else "review", selected=segmentation.status == "success", parameters={"target_ratio": round((rule["fill_min"] + rule["fill_max"]) / 2, 3)}))

        if segmentation.touches_edge:
            issue = _issue(
                "main.subject.safe-margin",
                severity="blocker",
                status="failed" if segmentation.status == "success" else "unknown",
                title="商品主体触碰画布边缘",
                description="图片可能存在裁切或安全边距不足，需要缩小主体或更换完整原图。",
                confidence=confidence,
                metrics={"touches_edge": True},
                auto_fix="resize_subject",
                requires_confirmation=True,
            )
            issues.append(issue)
            fix_plan.append(_fix(issue, "resize_subject", "review", selected=False, parameters={"safe_margin": 0.03}))

        white_ratio = metrics.get("white_pixel_ratio")
        if rule["white_background"] and isinstance(white_ratio, float) and white_ratio < 0.985:
            issue = _issue(
                "main.background.white",
                severity=rule["background_severity"],
                status="failed" if segmentation.status == "success" else "unknown",
                title="背景不是稳定纯白",
                description=f"主体外纯白像素比例约 {round(white_ratio * 100, 1)}%，建议更换为纯白背景。",
                confidence=confidence,
                metrics={"white_pixel_ratio": white_ratio},
                auto_fix="replace_background_white",
                requires_confirmation=segmentation.status != "success",
            )
            issues.append(issue)
            fix_plan.append(_fix(issue, "replace_background_white", "safe" if segmentation.status == "success" else "review", selected=segmentation.status == "success"))

    penalties = {"blocker": 30, "warning": 12, "quality": 5, "info": 0}
    score = 100.0
    for issue in issues:
        if issue["status"] in {"failed", "unknown"}:
            score -= penalties.get(issue["severity"], 5)
    if segmentation.status == "failed":
        score = min(score, 35.0)
    elif segmentation.status == "low_confidence":
        score = min(score, 70.0)
    score = max(0.0, score)

    blocker_failed = any(issue["severity"] == "blocker" and issue["status"] == "failed" for issue in issues)
    requires_review = any(issue["status"] == "unknown" or issue["requires_confirmation"] for issue in issues)
    if blocker_failed:
        status = "fail"
    elif requires_review or issues:
        status = "review"
    else:
        status = "pass"

    return PrecheckResult(
        status=status,
        score=score,
        rule_set_version=rule["rule_set_version"],
        segmentation=segmentation,
        metrics=metrics,
        issues=issues,
        fix_plan=fix_plan,
    )
