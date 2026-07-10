from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw

from app.services.precheck import analyze_source_image, segment_subject


def _transparent_product(path: Path, size: int = 320) -> None:
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 55, 240, 270), radius=24, fill=(40, 100, 220, 255))
    image.save(path, format="PNG")


def test_existing_alpha_produces_reusable_mask(tmp_path: Path) -> None:
    source = tmp_path / "product.png"
    _transparent_product(source)

    report = analyze_source_image(
        source,
        platform="amazon",
        marketplace="US",
        image_role="main",
        category="general",
    )

    assert report.segmentation.status == "success"
    assert report.segmentation.source == "alpha"
    assert report.segmentation.mask is not None
    assert report.segmentation.bbox is not None
    assert report.metrics["mask_area_ratio"] > 0
    assert report.rule_set_version.startswith("amazon-main")
    assert any(issue["id"] == "universal.file.min-dimensions" for issue in report.issues)


def test_full_rectangle_is_low_confidence() -> None:
    image = Image.new("RGBA", (300, 300), (20, 30, 40, 255))
    image.putalpha(Image.new("L", image.size, 255))

    def fake_remove(_payload: bytes) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    result = segment_subject(image.convert("RGB"), remove_fn=fake_remove)

    assert result.status == "low_confidence"
    assert result.rectangularity > 0.95
    assert result.foreground_area_ratio > 0.95
    assert any("完整矩形" in warning or "整张图片" in warning for warning in result.warnings)


def test_rembg_failure_never_falls_back_to_original_image() -> None:
    image = Image.new("RGB", (240, 240), (230, 230, 230))

    def broken_remove(_payload: bytes) -> bytes:
        raise RuntimeError("model unavailable")

    result = segment_subject(image, remove_fn=broken_remove)

    assert result.status == "failed"
    assert result.mask is None
    assert result.confidence == 0
    assert any("未将原始矩形图片" in warning for warning in result.warnings)
