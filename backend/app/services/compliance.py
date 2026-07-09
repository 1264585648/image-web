from __future__ import annotations

from dataclasses import dataclass
from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageStat


@dataclass(frozen=True)
class PlatformRuleSet:
    id: str
    name: str
    min_width: int
    min_height: int
    fill_min: float
    fill_max: float
    max_center_offset_x: float
    max_center_offset_y: float
    background_mode: str
    min_background_whiteness: float
    min_sharpness: float
    allow_shadow: bool


RULE_SETS: dict[str, PlatformRuleSet] = {
    "amazon-main-image": PlatformRuleSet(
        id="amazon-main-image",
        name="Amazon 白底主图规则",
        min_width=1000,
        min_height=1000,
        fill_min=0.75,
        fill_max=0.90,
        max_center_offset_x=0.04,
        max_center_offset_y=0.05,
        background_mode="pure_white",
        min_background_whiteness=248,
        min_sharpness=80,
        allow_shadow=False,
    ),
    "temu-main-image": PlatformRuleSet(
        id="temu-main-image",
        name="Temu 跨境主图规则",
        min_width=1000,
        min_height=1000,
        fill_min=0.68,
        fill_max=0.90,
        max_center_offset_x=0.05,
        max_center_offset_y=0.06,
        background_mode="pure_white",
        min_background_whiteness=245,
        min_sharpness=75,
        allow_shadow=False,
    ),
    "shopify-product-image": PlatformRuleSet(
        id="shopify-product-image",
        name="Shopify 商品图规则",
        min_width=1000,
        min_height=1000,
        fill_min=0.55,
        fill_max=0.92,
        max_center_offset_x=0.08,
        max_center_offset_y=0.08,
        background_mode="flexible",
        min_background_whiteness=0,
        min_sharpness=70,
        allow_shadow=True,
    ),
    "universal-transparent": PlatformRuleSet(
        id="universal-transparent",
        name="透明 PNG 素材规则",
        min_width=1000,
        min_height=1000,
        fill_min=0.60,
        fill_max=0.92,
        max_center_offset_x=0.08,
        max_center_offset_y=0.08,
        background_mode="transparent",
        min_background_whiteness=0,
        min_sharpness=70,
        allow_shadow=False,
    ),
    "universal-packshot": PlatformRuleSet(
        id="universal-packshot",
        name="通用棚拍素材规则",
        min_width=1000,
        min_height=1000,
        fill_min=0.60,
        fill_max=0.90,
        max_center_offset_x=0.07,
        max_center_offset_y=0.07,
        background_mode="white_or_light",
        min_background_whiteness=238,
        min_sharpness=70,
        allow_shadow=True,
    ),
    "mobile-commerce-cover": PlatformRuleSet(
        id="mobile-commerce-cover",
        name="移动端商品流规则",
        min_width=1000,
        min_height=1250,
        fill_min=0.58,
        fill_max=0.90,
        max_center_offset_x=0.08,
        max_center_offset_y=0.08,
        background_mode="white_or_light",
        min_background_whiteness=238,
        min_sharpness=70,
        allow_shadow=True,
    ),
}


def get_rule_set(rule_set_id: str | None) -> PlatformRuleSet:
    if rule_set_id and rule_set_id in RULE_SETS:
        return RULE_SETS[rule_set_id]
    return RULE_SETS["amazon-main-image"]


def _item(
    item_id: str,
    label: str,
    status: str,
    message: str,
    *,
    passed: bool | None = None,
    actual: str | float | int | None = None,
    expected: str | float | int | None = None,
    severity: str = "warning",
) -> dict[str, str | bool | float | int | None]:
    return {
        "id": item_id,
        "label": label,
        "status": status,
        "passed": passed,
        "severity": severity,
        "actual": actual,
        "expected": expected,
        "message": message,
    }


@dataclass
class ComplianceResult:
    score: float
    checks: dict[str, bool]
    metrics: dict[str, float | int | str]
    warnings: list[str]
    rule_set_id: str
    rule_set_name: str
    items: list[dict[str, str | bool | float | int | None]]
    recommendations: list[str]
    qc_status: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "checks": self.checks,
            "metrics": self.metrics,
            "warnings": self.warnings,
            "rule_set_id": self.rule_set_id,
            "rule_set_name": self.rule_set_name,
            "items": self.items,
            "recommendations": self.recommendations,
            "qc_status": self.qc_status,
        }


def _product_bbox_from_alpha(image: Image.Image) -> tuple[int, int, int, int] | None:
    if image.mode != "RGBA":
        return None
    alpha = image.getchannel("A")
    return alpha.point(lambda p: 255 if p > 16 else 0).getbbox()


def _product_bbox_from_background(image: Image.Image, background_rgb=(255, 255, 255)) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    bg = Image.new("RGB", rgb.size, background_rgb)
    diff = ImageChops.difference(rgb, bg).convert("L")
    mask = diff.point(lambda p: 255 if p > 18 else 0)
    return mask.getbbox()


def _expected_background_rgb(background: str) -> tuple[int, int, int]:
    if background == "light-gray":
        return (248, 250, 252)
    if background.startswith("#"):
        try:
            return ImageColor.getrgb(background)[:3]
        except ValueError:
            return (255, 255, 255)
    return (255, 255, 255)


def _background_whiteness(image: Image.Image, bbox: tuple[int, int, int, int] | None) -> float:
    rgb = image.convert("RGB")
    w, h = rgb.size
    mask = Image.new("L", (w, h), 255)
    if bbox:
        x1, y1, x2, y2 = bbox
        pad = max(8, int(min(w, h) * 0.02))
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        mask.paste(0, (x1, y1, x2, y2))
    if mask.getbbox() is None:
        return 0.0
    stat = ImageStat.Stat(rgb, mask)
    mean = stat.mean
    return round(sum(mean) / 3, 2)


def _blur_score(image: Image.Image) -> float:
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    return round(stat.var[0], 2)


def _background_check(
    rule_set: PlatformRuleSet,
    image: Image.Image,
    bbox: tuple[int, int, int, int] | None,
    expected_background: str,
) -> tuple[bool, str, float]:
    whiteness = _background_whiteness(image, bbox)
    if rule_set.background_mode == "transparent":
        alpha_ok = image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255
        return alpha_ok, "透明背景素材需要保留透明通道。", whiteness
    if rule_set.background_mode == "flexible":
        return True, "该平台规则允许更灵活的背景。", whiteness
    if rule_set.background_mode == "white_or_light":
        ok = expected_background in {"white", "light-gray"} or whiteness >= rule_set.min_background_whiteness
        return ok, "背景建议使用纯白或浅色，方便商品主体识别。", whiteness
    ok = expected_background == "white" and whiteness >= rule_set.min_background_whiteness
    return ok, "主图背景需要接近纯白。", whiteness


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def analyze_image(
    image: Image.Image,
    expected_background: str = "white",
    *,
    rule_set_id: str | None = None,
    shadow_added: bool | None = None,
) -> ComplianceResult:
    rule_set = get_rule_set(rule_set_id)
    width, height = image.size
    if expected_background == "transparent":
        bbox = _product_bbox_from_alpha(image) or _product_bbox_from_background(image)
    else:
        bbox = _product_bbox_from_background(image, _expected_background_rgb(expected_background)) or _product_bbox_from_alpha(image)

    warnings: list[str] = []
    recommendations: list[str] = []
    items: list[dict[str, str | bool | float | int | None]] = []
    checks: dict[str, bool] = {}
    metrics: dict[str, float | int | str] = {
        "width": width,
        "height": height,
        "background": expected_background,
        "rule_set_id": rule_set.id,
        "rule_set_name": rule_set.name,
    }
    qc_status = {
        "ocr_text": "not_run",
        "watermark": "not_run",
        "logo_consistency": "not_run",
    }

    size_ok = width >= rule_set.min_width and height >= rule_set.min_height
    checks["size_ok"] = size_ok
    items.append(
        _item(
            "size",
            "尺寸",
            "pass" if size_ok else "fail",
            "图片尺寸满足当前平台要求。" if size_ok else f"建议导出至少 {rule_set.min_width}×{rule_set.min_height} 像素。",
            passed=size_ok,
            actual=f"{width}×{height}",
            expected=f">= {rule_set.min_width}×{rule_set.min_height}",
            severity="fail",
        )
    )
    if not size_ok:
        warnings.append("图片尺寸偏小，建议提高导出尺寸。")
        recommendations.append(f"将导出尺寸调整到至少 {rule_set.min_width}×{rule_set.min_height} 像素。")

    if bbox is None:
        warnings.append("未能稳定识别商品主体，请检查商品是否与背景区分明显。")
        checks.update({
            "product_detected": False,
            "centered": False,
            "fill_ratio_ok": False,
            "sharpness_ok": False,
            "background_ok": expected_background == "transparent",
            "shadow_ok": not shadow_added or rule_set.allow_shadow,
        })
        items.append(
            _item(
                "product_detected",
                "商品主体",
                "fail",
                "未能稳定识别商品主体。",
                passed=False,
                severity="fail",
            )
        )
        for item_id, label in [("ocr_text", "文字检测"), ("watermark", "水印检测"), ("logo_consistency", "Logo 一致性")]:
            items.append(_item(item_id, label, "not_run", "高级质检接口已预留，本期未运行。", severity="info"))
        recommendations.append("换一张主体边缘更清晰、背景更干净的商品图后重试。")
        return ComplianceResult(
            score=35,
            checks=checks,
            metrics=metrics,
            warnings=_dedupe(warnings),
            rule_set_id=rule_set.id,
            rule_set_name=rule_set.name,
            items=items,
            recommendations=_dedupe(recommendations),
            qc_status=qc_status,
        )

    x1, y1, x2, y2 = bbox
    product_w = x2 - x1
    product_h = y2 - y1
    fill_ratio = max(product_w / width, product_h / height)
    product_cx = x1 + product_w / 2
    product_cy = y1 + product_h / 2
    center_offset_x = abs(product_cx - width / 2) / width
    center_offset_y = abs(product_cy - height / 2) / height
    background_ok, background_message, whiteness = _background_check(rule_set, image, bbox, expected_background)
    blur = _blur_score(image)

    metrics.update(
        {
            "product_fill_ratio": round(fill_ratio, 3),
            "center_offset_x": round(center_offset_x, 3),
            "center_offset_y": round(center_offset_y, 3),
            "background_whiteness": whiteness,
            "sharpness_score": blur,
            "expected_fill_min": rule_set.fill_min,
            "expected_fill_max": rule_set.fill_max,
        }
    )

    checks["product_detected"] = True
    checks["centered"] = center_offset_x <= rule_set.max_center_offset_x and center_offset_y <= rule_set.max_center_offset_y
    checks["fill_ratio_ok"] = rule_set.fill_min <= fill_ratio <= rule_set.fill_max
    checks["sharpness_ok"] = blur >= rule_set.min_sharpness
    checks["background_ok"] = background_ok
    checks["shadow_ok"] = not shadow_added or rule_set.allow_shadow

    items.append(
        _item(
            "product_detected",
            "商品主体",
            "pass",
            "已识别到商品主体。",
            passed=True,
            severity="fail",
        )
    )
    items.append(
        _item(
            "background",
            "背景",
            "pass" if checks["background_ok"] else "fail",
            background_message if not checks["background_ok"] else "背景满足当前平台规则。",
            passed=checks["background_ok"],
            actual=round(whiteness, 2),
            expected=rule_set.background_mode,
            severity="fail" if rule_set.background_mode == "pure_white" else "warning",
        )
    )
    items.append(
        _item(
            "centered",
            "商品居中",
            "pass" if checks["centered"] else "warning",
            "商品主体居中。" if checks["centered"] else "商品主体不够居中。",
            passed=checks["centered"],
            actual=f"{center_offset_x:.3f}, {center_offset_y:.3f}",
            expected=f"<= {rule_set.max_center_offset_x}, {rule_set.max_center_offset_y}",
        )
    )
    items.append(
        _item(
            "fill_ratio",
            "商品占比",
            "pass" if checks["fill_ratio_ok"] else "warning",
            "商品占比在推荐范围内。" if checks["fill_ratio_ok"] else f"商品占比建议控制在 {int(rule_set.fill_min * 100)}%-{int(rule_set.fill_max * 100)}%。",
            passed=checks["fill_ratio_ok"],
            actual=round(fill_ratio, 3),
            expected=f"{rule_set.fill_min:.2f}-{rule_set.fill_max:.2f}",
        )
    )
    items.append(
        _item(
            "sharpness",
            "清晰度",
            "pass" if checks["sharpness_ok"] else "warning",
            "图片清晰度满足要求。" if checks["sharpness_ok"] else "图片清晰度偏低。",
            passed=checks["sharpness_ok"],
            actual=blur,
            expected=f">= {rule_set.min_sharpness}",
        )
    )
    items.append(
        _item(
            "shadow",
            "阴影",
            "pass" if checks["shadow_ok"] else "warning",
            "阴影设置符合当前规则。" if checks["shadow_ok"] else "当前平台主图不建议添加阴影。",
            passed=checks["shadow_ok"],
            actual="已添加" if shadow_added else "未添加",
            expected="允许" if rule_set.allow_shadow else "不建议",
        )
    )
    for item_id, label in [("ocr_text", "文字检测"), ("watermark", "水印检测"), ("logo_consistency", "Logo 一致性")]:
        items.append(_item(item_id, label, "not_run", "高级质检接口已预留，本期未运行。", severity="info"))

    if not checks["centered"]:
        warnings.append("商品主体不够居中，可能影响平台主图观感。")
        recommendations.append("调整画布或重新生成，让主体水平和垂直方向更居中。")
    if not checks["fill_ratio_ok"]:
        warnings.append("商品占比不在当前平台推荐范围。")
        recommendations.append(f"将商品占比控制在 {int(rule_set.fill_min * 100)}% 到 {int(rule_set.fill_max * 100)}%。")
    if not checks["background_ok"]:
        warnings.append(background_message)
        recommendations.append("切换为纯白或平台允许的浅色背景后重新生成。")
    if not checks["sharpness_ok"]:
        warnings.append("图片清晰度偏低，建议上传更清晰的原图或开启清晰化。")
        recommendations.append("上传更高清的商品图，或开启自动补光和清晰化。")
    if not checks["shadow_ok"]:
        warnings.append("当前平台主图不建议添加阴影。")
        recommendations.append("关闭自然阴影后重新生成当前平台主图。")

    score = 100
    penalties = {
        "size_ok": 12,
        "centered": 14,
        "fill_ratio_ok": 18,
        "background_ok": 22,
        "sharpness_ok": 10,
        "shadow_ok": 8,
    }
    for check, penalty in penalties.items():
        if not checks[check]:
            score -= penalty

    return ComplianceResult(
        score=max(float(score), 0.0),
        checks=checks,
        metrics=metrics,
        warnings=_dedupe(warnings),
        rule_set_id=rule_set.id,
        rule_set_name=rule_set.name,
        items=items,
        recommendations=_dedupe(recommendations),
        qc_status=qc_status,
    )
