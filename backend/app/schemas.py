from datetime import datetime
from typing import Any

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


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


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
    sharpen: bool = True
    output_format: str = Field(default="png", pattern="^(png|jpg|jpeg|webp)$")


class ComplianceReport(BaseModel):
    score: float
    checks: dict[str, bool]
    metrics: dict[str, float | int | str]
    warnings: list[str]


class ComplianceAnalyzeRequest(BaseModel):
    source_image_id: str
    platform: str = Field(default="amazon", pattern="^(amazon|google-merchant|universal)$")
    marketplace: str | None = Field(default="US", max_length=40)
    image_role: str = Field(default="main", pattern="^(main|secondary|product-image)$")
    category: str = Field(default="general", min_length=1, max_length=120)


class ComplianceContextOut(BaseModel):
    platform: str
    marketplace: str | None
    image_role: str
    category: str
    rule_set_version: str


class SegmentationOut(BaseModel):
    status: str
    confidence: float
    mask_url: str | None = None
    bbox: list[int] | None = None
    foreground_area_ratio: float
    touches_edge: bool
    rectangularity: float
    source: str
    warnings: list[str] = Field(default_factory=list)


class ComplianceIssueOut(BaseModel):
    id: str
    rule_id: str
    severity: str
    status: str
    title: str
    description: str
    confidence: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    auto_fix: str | None = None
    requires_confirmation: bool = False


class FixActionOut(BaseModel):
    id: str
    issue_id: str
    action: str
    risk: str
    selected_by_default: bool
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False


class ComplianceAnalysisOut(BaseModel):
    id: str
    source_image_id: str
    context: ComplianceContextOut
    status: str
    score: float
    segmentation: SegmentationOut
    metrics: dict[str, Any]
    issues: list[ComplianceIssueOut]
    fix_plan: list[FixActionOut]
    created_at: datetime


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
