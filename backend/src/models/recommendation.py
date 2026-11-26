from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class Recommendation(Base):
    """Persistent per-buckle advice work item; natural key prevents duplicate tickets."""

    __tablename__ = 'retest_recommendations'
    __table_args__ = (
        UniqueConstraint('run_id', 'part_id', name='uq_retest_recommendations_run_part'),
        Index('ix_retest_recommendations_run_status', 'run_id', 'status'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('analysis_runs.id'), index=True)
    part_id: Mapped[str] = mapped_column(String(40))
    clip_variant: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), index=True)
    found: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reference_part: Mapped[str | None] = mapped_column(String(40), nullable=True)
    measurements: Mapped[list] = mapped_column(JSON, default=list)
    replacement_readings: Mapped[dict] = mapped_column(JSON, default=dict)
    total_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
