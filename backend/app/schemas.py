from datetime import datetime
from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    id: str
    name: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    background: str
    product_fill_ratio: float
    shadow_enabled: bool
    description: str


class SourceImageOut(BaseModel):
    id: str
    original_filename: str
    public_url: str
    width: int
    height: int
    content_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    source_image_id: str
    template_id: str = "amazon-white-main"
    width: int | None = Field(default=None, ge=512, le=4096)
    height: int | None = Field(default=None, ge=512, le=4096)
    product_fill_ratio: float | None = Field(default=None, ge=0.45, le=0.92)
    background: str | None = Field(default=None, description="white, transparent, light-gray or hex color")
    add_shadow: bool | None = None
    auto_enhance: bool = True
    edge_repair: bool = True
    output_format: str = Field(default="png", pattern="^(png|jpg|jpeg|webp)$")


class ComplianceReport(BaseModel):
    score: float
    checks: dict[str, bool]
    metrics: dict[str, float | int | str]
    warnings: list[str]


class AssetOut(BaseModel):
    id: str
    output_type: str
    public_url: str
    width: int
    height: int
    compliance: ComplianceReport | None = None
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    source_image_id: str
    template_id: str
    status: str
    progress: int = 0
    current_step: str | None = None
    error_message: str | None
    compliance_score: float | None
    created_at: datetime
    updated_at: datetime
    assets: list[AssetOut] = []


class HistoryOut(BaseModel):
    tasks: list[TaskOut]
