from __future__ import annotations

import io
from pathlib import Path
from PIL import Image, ImageColor, ImageEnhance, ImageFilter, ImageOps

from app.schemas import GenerateRequest
from app.templates import get_template
from app.services.compliance import analyze_image, ComplianceResult


def _open_image(path: str | Path) -> Image.Image:
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    return image.convert("RGBA")


def _remove_background(image: Image.Image) -> Image.Image:
    # Preserve existing transparency when users upload PNG/WebP with alpha.
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255:
        return image

    try:
        from rembg import remove  # type: ignore

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        output = remove(buffer.getvalue())
        return Image.open(io.BytesIO(output)).convert("RGBA")
    except Exception:
        # Fallback keeps the original image as the subject. This makes local dev easy,
        # but production should install rembg or connect a commercial background-removal API.
        return image.convert("RGBA")


def _repair_alpha_edge(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image.convert("RGBA")
    r, g, b, a = image.split()
    a = a.filter(ImageFilter.MedianFilter(size=3))
    a = a.filter(ImageFilter.GaussianBlur(radius=0.35))
    return Image.merge("RGBA", (r, g, b, a))


def _auto_enhance(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    rgb = ImageOps.autocontrast(rgb, cutoff=1)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.03)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.05)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.08)
    if image.mode == "RGBA":
        rgb.putalpha(image.getchannel("A"))
    return rgb.convert("RGBA")


def _subject_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda p: 255 if p > 10 else 0).getbbox()
    if bbox:
        return bbox
    return (0, 0, image.width, image.height)


def _parse_background_color(background: str) -> tuple[int, int, int, int]:
    if background == "light-gray":
        return (248, 250, 252, 255)
    if background.startswith("#"):
        try:
            color = ImageColor.getcolor(background, "RGBA")
            return color
        except ValueError:
            return (255, 255, 255, 255)
    return (255, 255, 255, 255)


def _background_canvas(width: int, height: int, background: str) -> Image.Image:
    if background == "transparent":
        return Image.new("RGBA", (width, height), (255, 255, 255, 0))
    return Image.new("RGBA", (width, height), _parse_background_color(background))


def _add_shadow(canvas: Image.Image, subject: Image.Image, x: int, y: int) -> None:
    alpha = subject.getchannel("A")
    shadow = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda p: int(p * 0.23)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(12, int(subject.width * 0.025))))
    offset_y = max(12, int(subject.height * 0.035))
    canvas.alpha_composite(shadow, (x, y + offset_y))


def prepare_subject(source_path: str | Path, *, edge_repair: bool = True, auto_enhance: bool = True) -> Image.Image:
    """Run the expensive subject preparation once and reuse it for all output variants."""
    image = _open_image(source_path)
    subject = _remove_background(image)
    if edge_repair:
        subject = _repair_alpha_edge(subject)
    if auto_enhance:
        subject = _auto_enhance(subject)
    return subject.crop(_subject_bbox(subject))


def compose_subject_image(
    subject_image: Image.Image,
    request: GenerateRequest,
    output_path: str | Path,
) -> tuple[Path, ComplianceResult]:
    template = get_template(request.template_id)
    width = request.width or template.width
    height = request.height or template.height
    fill = request.product_fill_ratio or template.product_fill_ratio
    background = request.background or template.background
    add_shadow = template.shadow_enabled if request.add_shadow is None else request.add_shadow

    subject = subject_image.copy()
    max_w = int(width * fill)
    max_h = int(height * fill)
    scale = min(max_w / subject.width, max_h / subject.height)
    new_size = (max(1, int(subject.width * scale)), max(1, int(subject.height * scale)))
    subject = subject.resize(new_size, Image.Resampling.LANCZOS)

    canvas = _background_canvas(width, height, background)
    x = (width - subject.width) // 2
    y = (height - subject.height) // 2

    if add_shadow and background != "transparent":
        _add_shadow(canvas, subject, x, y)
    canvas.alpha_composite(subject, (x, y))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = request.output_format.lower()
    if fmt in {"jpg", "jpeg"}:
        canvas.convert("RGB").save(output_path, format="JPEG", quality=94, optimize=True)
    elif fmt == "webp":
        canvas.save(output_path, format="WEBP", quality=94, method=6)
    else:
        canvas.save(output_path, format="PNG", optimize=True)

    report = analyze_image(canvas, expected_background=background)
    return output_path, report


def compose_main_image(
    source_path: str | Path,
    request: GenerateRequest,
    output_path: str | Path,
) -> tuple[Path, ComplianceResult]:
    subject = prepare_subject(
        source_path,
        edge_repair=request.edge_repair,
        auto_enhance=request.auto_enhance,
    )
    return compose_subject_image(subject, request, output_path)
