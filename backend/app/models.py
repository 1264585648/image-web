from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source_images: Mapped[list["SourceImage"]] = relationship(back_populates="user")
    tasks: Mapped[list["GenerationTask"]] = relationship(back_populates="user")
    compliance_analyses: Mapped[list["ComplianceAnalysis"]] = relationship(back_populates="user")


class SourceImage(Base):
    __tablename__ = "source_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    public_url: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User | None] = relationship(back_populates="source_images")
    tasks: Mapped[list["GenerationTask"]] = relationship(back_populates="source_image")
    compliance_analyses: Mapped[list["ComplianceAnalysis"]] = relationship(back_populates="source_image")


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    source_image_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_images.id"))
    template_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_json: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User | None] = relationship(back_populates="tasks")
    source_image: Mapped[SourceImage] = relationship(back_populates="tasks")
    assets: Mapped[list["GeneratedAsset"]] = relationship(back_populates="task")


class GeneratedAsset(Base):
    __tablename__ = "generated_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("generation_tasks.id"))
    output_type: Mapped[str] = mapped_column(String(80))
    file_path: Mapped[str] = mapped_column(Text)
    public_url: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    compliance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped[GenerationTask] = relationship(back_populates="assets")


class ComplianceAnalysis(Base):
    __tablename__ = "compliance_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    source_image_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_images.id"), index=True)
    platform: Mapped[str] = mapped_column(String(40))
    marketplace: Mapped[str | None] = mapped_column(String(40), nullable=True)
    image_role: Mapped[str] = mapped_column(String(40), default="main")
    category: Mapped[str] = mapped_column(String(120), default="general")
    rule_set_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    segmentation_status: Mapped[str] = mapped_column(String(30))
    segmentation_confidence: Mapped[float] = mapped_column(Float)
    segmentation_json: Mapped[str] = mapped_column(Text)
    mask_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[str] = mapped_column(Text)
    issues_json: Mapped[str] = mapped_column(Text)
    fix_plan_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="compliance_analyses")
    source_image: Mapped[SourceImage] = relationship(back_populates="compliance_analyses")
