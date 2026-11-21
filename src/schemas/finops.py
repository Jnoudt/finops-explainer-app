"""Pydantic response models for the FinOps dashboard."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high", "critical"]
AnomalyDirection = Literal["increase", "decrease"]


class FinOpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DailyCostPoint(FinOpsModel):
    date: date
    service_name: str = Field(min_length=1)
    amount: Decimal
    currency: str = Field(default="USD", min_length=3, max_length=3)


class AnomalyFinding(FinOpsModel):
    date: date
    service_name: str = Field(min_length=1)
    actual_cost: Decimal
    baseline_cost: Decimal
    delta_amount: Decimal
    delta_percentage: Decimal | None
    z_score: Decimal | None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    severity: Severity
    direction: AnomalyDirection


class RunSummary(FinOpsModel):
    start_date: date
    end_date: date
    total_cost: Decimal
    currency: str = Field(default="USD", min_length=3, max_length=3)
    point_count: int = Field(ge=0)
    service_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    source_mode: Literal["demo", "live"]


class NarrativeOutput(FinOpsModel):
    text: str
    generated_at: datetime
    provider: str = Field(min_length=1)


class CheckedClaim(FinOpsModel):
    figure: str
    supported: bool
    matched_field: str | None = None


class FactCheckVerdict(FinOpsModel):
    accepted: bool
    checked_claims: tuple[CheckedClaim, ...]
    unsupported_claims: tuple[str, ...]


class DashboardPayload(FinOpsModel):
    correlation_id: str = Field(min_length=1)
    summary: RunSummary
    daily_costs: tuple[DailyCostPoint, ...]
    anomalies: tuple[AnomalyFinding, ...]
    narrative: NarrativeOutput | None = None
    fact_check: FactCheckVerdict | None = None
