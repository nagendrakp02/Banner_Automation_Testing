"""db/models.py"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Float, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def _uuid(): return str(uuid.uuid4())
def _now(): return datetime.utcnow()

class Base(DeclarativeBase): pass

class Banner(Base):
    __tablename__ = "banners"
    id:         Mapped[str]       = mapped_column(String(36), primary_key=True, default=_uuid)
    url_id:     Mapped[str]       = mapped_column(String(64), unique=True)
    name:       Mapped[str]       = mapped_column(String(255))
    url:        Mapped[str]       = mapped_column(Text)
    client:     Mapped[str|None]  = mapped_column(String(128))
    dimensions: Mapped[str|None]  = mapped_column(String(32))
    is_active:  Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=_now)
    runs: Mapped[list["TestRun"]] = relationship("TestRun", back_populates="banner")

class TestRun(Base):
    __tablename__ = "test_runs"
    id:                     Mapped[str]       = mapped_column(String(36), primary_key=True, default=_uuid)
    banner_id:              Mapped[str]       = mapped_column(String(36), ForeignKey("banners.id"))
    status:                 Mapped[str]       = mapped_column(String(32), default="pending")
    triggered_by:           Mapped[str]       = mapped_column(String(128), default="manual")
    total_checks:           Mapped[int]       = mapped_column(Integer, default=0)
    passed_checks:          Mapped[int]       = mapped_column(Integer, default=0)
    failed_checks:          Mapped[int]       = mapped_column(Integer, default=0)
    error_checks:           Mapped[int]       = mapped_column(Integer, default=0)
    started_at:             Mapped[datetime|None] = mapped_column(DateTime)
    completed_at:           Mapped[datetime|None] = mapped_column(DateTime)
    orchestrator_reasoning: Mapped[str|None]  = mapped_column(Text)
    created_at:             Mapped[datetime]  = mapped_column(DateTime, default=_now)
    banner:        Mapped["Banner"]           = relationship("Banner", back_populates="runs")
    check_results: Mapped[list["CheckResult"]] = relationship("CheckResult", back_populates="run")

class CheckResult(Base):
    __tablename__ = "check_results"
    id:              Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id:          Mapped[str]        = mapped_column(String(36), ForeignKey("test_runs.id"))
    check_id:        Mapped[str]        = mapped_column(String(64))
    check_name:      Mapped[str]        = mapped_column(String(128))
    agent_name:      Mapped[str]        = mapped_column(String(64))
    status:          Mapped[str]        = mapped_column(String(32), default="pending")
    raw_data:        Mapped[dict|None]  = mapped_column(JSON)
    llm_reasoning:   Mapped[str|None]   = mapped_column(Text)
    llm_verdict:     Mapped[str|None]   = mapped_column(String(32))
    final_verdict:   Mapped[str|None]   = mapped_column(String(32))
    screenshot_path: Mapped[str|None]   = mapped_column(Text)
    duration_ms:     Mapped[float|None] = mapped_column(Float)
    error_message:   Mapped[str|None]   = mapped_column(Text)
    executed_at:     Mapped[datetime|None] = mapped_column(DateTime)
    run: Mapped["TestRun"] = relationship("TestRun", back_populates="check_results")