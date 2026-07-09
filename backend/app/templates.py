from app.schemas import TemplateOut

TEMPLATES: dict[str, TemplateOut] = {
    "amazon-white-main": TemplateOut(
        id="amazon-white-main",
        name="Amazon 白底主图",
        platform="Amazon",
        aspect_ratio="1:1",
        width=2000,
        height=2000,
        background="white",
        product_fill_ratio=0.85,
        shadow_enabled=False,
        description="纯白背景、商品居中、适合商品主图上传。",
    ),
    "temu-white-main": TemplateOut(
        id="temu-white-main",
        name="Temu 跨境主图",
        platform="Temu",
        aspect_ratio="1:1",
        width=1600,
        height=1600,
        background="white",
        product_fill_ratio=0.82,
        shadow_enabled=False,
        description="白底或浅背景、商品主体清晰居中。",
    ),
    "shopify-main": TemplateOut(
        id="shopify-main",
        name="Shopify 独立站主图",
        platform="Shopify",
        aspect_ratio="1:1",
        width=1600,
        height=1600,
        background="white",
        product_fill_ratio=0.78,
        shadow_enabled=True,
        description="适合独立站首页、产品列表和详情页首图。",
    ),
    "transparent-png": TemplateOut(
        id="transparent-png",
        name="透明 PNG",
        platform="Universal",
        aspect_ratio="1:1",
        width=2000,
        height=2000,
        background="transparent",
        product_fill_ratio=0.86,
        shadow_enabled=False,
        description="透明背景，方便后续做海报、详情图和广告素材。",
    ),
    "soft-shadow-packshot": TemplateOut(
        id="soft-shadow-packshot",
        name="轻阴影棚拍图",
        platform="Universal",
        aspect_ratio="1:1",
        width=2000,
        height=2000,
        background="white",
        product_fill_ratio=0.78,
        shadow_enabled=True,
        description="白底加自然柔和阴影，更接近专业棚拍效果。",
    ),
    "mobile-cover-4x5": TemplateOut(
        id="mobile-cover-4x5",
        name="移动端 4:5 主图",
        platform="Mobile Commerce",
        aspect_ratio="4:5",
        width=1600,
        height=2000,
        background="white",
        product_fill_ratio=0.80,
        shadow_enabled=True,
        description="适合移动端商品流、广告封面和社媒商品图。",
    ),
}


def get_template(template_id: str) -> TemplateOut:
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown template_id: {template_id}")
    return TEMPLATES[template_id]
