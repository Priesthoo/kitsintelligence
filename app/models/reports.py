"""Report generation domain model — tracks async report jobs (PDF/Excel/CSV exports)."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin


class ReportFormat(StrEnum):
    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"


class ReportStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False, default=ReportFormat.PDF.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReportStatus.QUEUED.value)
    parameters_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_reports_org_status", "organization_id", "status"),)