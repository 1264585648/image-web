from __future__ import annotations

from dataclasses import dataclass
from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageStat


@dataclass
class ComplianceResult:
    score: float
    checks: dict[str, bool]
    metrics: dict[str, float | int | str]
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "checks": self.checks,
            "metrics": self.metrics,
            "warnings": self.warnings,
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


def analyze_image(image: Image.Image, expected_background: str = "white") -> ComplianceResult:
    width, height = image.size
    if expected_background == "transparent":
        bbox = _product_bbox_from_alpha(image) or _product_bbox_from_background(image)
    else:
        bbox = _product_bbox_from_background(image, _expected_background_rgb(expected_background)) or _product_bbox_from_alpha(image)

    warnings: list[str] = []
    checks: dict[str, bool] = {}
    metrics: dict[str, float | int | str] = {
        "width": width,
        "height": height,
        "background": expected_background,
    }

    if bbox is None:
        warnings.append("未能稳定识别商品主体，请检查商品是否与背景区分明显。")
        checks.update({
            "product_detected": False,
            "centered": False,
            "fill_ratio_ok": False,
            "size_ok": width >= 1000 and height >= 1000,
            "background_ok": expected_background == "transparent",
            "sharpness_ok": False,
        })
        return ComplianceResult(score=35, checks=checks, metrics=metrics, warnings=warnings)

    x1, y1, x2, y2 = bbox
    product_w = x2 - x1
    product_h = y2 - y1
    fill_ratio = max(product_w / width, product_h / height)
    product_cx = x1 + product_w / 2
    product_cy = y1 + product_h / 2
    center_offset_x = abs(product_cx - width / 2) / width
    center_offset_y = abs(product_cy - height / 2) / height
    whiteness = _background_whiteness(image, bbox)
    blur = _blur_score(image)

    metrics.update(
        {
            "product_fill_ratio": round(fill_ratio, 3),
            "center_offset_x": round(center_offset_x, 3),
            "center_offset_y": round(center_offset_y, 3),
            "background_whiteness": whiteness,
            "sharpness_score": blur,
        }
    )

    checks["product_detected"] = True
    checks["size_ok"] = width >= 1000 and height >= 1000
    checks["centered"] = center_offset_x <= 0.04 and center_offset_y <= 0.05
    checks["fill_ratio_ok"] = 0.65 <= fill_ratio <= 0.90
    checks["sharpness_ok"] = blur >= 80
    checks["background_ok"] = expected_background == "transparent" or whiteness >= 248

    if not checks["size_ok"]:
        warnings.append("图片尺寸偏小，建议导出 1000px 以上，最好 1600px 或 2000px。")
    if not checks["centered"]:
        warnings.append("商品主体不够居中，可能影响平台主图观感。")
    if not checks["fill_ratio_ok"]:
        warnings.append("商品占比不在推荐范围，建议控制在 65% 到 90%。")
    if not checks["background_ok"]:
        warnings.append("背景不够接近纯白，部分平台主图可能审核不通过。")
    if not checks["sharpness_ok"]:
        warnings.append("图片清晰度偏低，建议上传更清晰的原图或开启清晰化。")

    score = 100
    penalties = {
        "size_ok": 12,
        "centered": 14,
        "fill_ratio_ok": 18,
        "background_ok": 22,
        "sharpness_ok": 10,
    }
    for check, penalty in penalties.items():
        if not checks[check]:
            score -= penalty

    return ComplianceResult(score=max(float(score), 0.0), checks=checks, metrics=metrics, warnings=warnings)
