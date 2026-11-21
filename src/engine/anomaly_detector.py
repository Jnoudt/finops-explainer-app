"""Rolling deterministic cost anomaly detection using Decimal arithmetic."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, pstdev
from typing import Iterable

from src.config import Mode
from src.schemas.finops import AnomalyFinding, DailyCostPoint, RunSummary, Severity

CENT = Decimal("0.01")
SCORE_QUANTUM = Decimal("0.01")


def detect_anomalies(
    points: Iterable[DailyCostPoint],
    *,
    window_size: int = 14,
    min_periods: int = 7,
    z_score_threshold: Decimal = Decimal("3.00"),
    delta_percentage_threshold: Decimal = Decimal("50.00"),
) -> list[AnomalyFinding]:
    """Compare each point to the preceding rolling window for its service."""
    if window_size < 1:
        raise ValueError("window_size must be at least 1.")
    if min_periods < 2 or min_periods > window_size:
        raise ValueError("min_periods must be between 2 and window_size.")
    if z_score_threshold <= 0 or delta_percentage_threshold < 0:
        raise ValueError(
            "Anomaly thresholds must be non-negative and z-score positive."
        )

    by_service: dict[str, list[DailyCostPoint]] = defaultdict(list)
    for point in points:
        by_service[point.service_name].append(point)

    findings: list[AnomalyFinding] = []
    for service_name in sorted(by_service):
        series = sorted(by_service[service_name], key=lambda point: point.date)
        if len({point.date for point in series}) != len(series):
            raise ValueError(
                f"Duplicate daily costs found for service {service_name!r}."
            )

        history: list[DailyCostPoint] = []
        for point in series:
            if len(history) >= min_periods:
                baseline_values = [prior.amount for prior in history[-window_size:]]
                baseline = mean(baseline_values)
                delta = (point.amount - baseline).quantize(CENT, rounding=ROUND_HALF_UP)
                percentage = (
                    (delta / baseline * Decimal("100")).quantize(
                        SCORE_QUANTUM, rounding=ROUND_HALF_UP
                    )
                    if baseline != 0
                    else None
                )
                deviation = pstdev(baseline_values)
                z_score = (
                    ((point.amount - baseline) / deviation).quantize(
                        SCORE_QUANTUM, rounding=ROUND_HALF_UP
                    )
                    if deviation != 0
                    else None
                )
                is_anomaly = (
                    (z_score is not None and abs(z_score) >= z_score_threshold)
                    or (
                        percentage is not None
                        and abs(percentage) >= delta_percentage_threshold
                    )
                    or (baseline == 0 and point.amount != 0)
                )
                if is_anomaly:
                    findings.append(
                        AnomalyFinding(
                            date=point.date,
                            service_name=service_name,
                            actual_cost=point.amount.quantize(
                                CENT, rounding=ROUND_HALF_UP
                            ),
                            baseline_cost=baseline.quantize(
                                CENT, rounding=ROUND_HALF_UP
                            ),
                            delta_amount=delta,
                            delta_percentage=percentage,
                            z_score=z_score,
                            currency=point.currency,
                            severity=_severity(percentage, z_score),
                            direction="increase" if delta > 0 else "decrease",
                        )
                    )
            history.append(point)
    return sorted(findings, key=lambda item: (item.date, item.service_name))


def build_run_summary(
    points: Iterable[DailyCostPoint],
    findings: Iterable[AnomalyFinding],
    *,
    source_mode: Mode,
) -> RunSummary:
    """Aggregate run-level metrics without introducing binary floats."""
    point_list = list(points)
    finding_list = list(findings)
    if source_mode not in ("demo", "live"):
        raise ValueError("source_mode must be either 'demo' or 'live'.")
    if not point_list:
        raise ValueError("Cannot summarize an empty cost result.")
    currencies = {point.currency for point in point_list}
    if len(currencies) != 1:
        raise ValueError("Cannot aggregate costs in multiple currencies.")
    dates = [point.date for point in point_list]
    return RunSummary(
        start_date=min(dates),
        end_date=max(dates),
        total_cost=sum((point.amount for point in point_list), start=Decimal("0")),
        currency=currencies.pop(),
        point_count=len(point_list),
        service_count=len({point.service_name for point in point_list}),
        anomaly_count=len(finding_list),
        source_mode=source_mode,
    )


def _severity(percentage: Decimal | None, z_score: Decimal | None) -> Severity:
    abs_percentage = abs(percentage) if percentage is not None else Decimal("0")
    abs_z_score = abs(z_score) if z_score is not None else Decimal("0")
    if abs_z_score >= Decimal("5") or abs_percentage >= Decimal("200"):
        return "critical"
    if abs_z_score >= Decimal("3") or abs_percentage >= Decimal("100"):
        return "high"
    return "medium"
