from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.engine.anomaly_detector import build_run_summary, detect_anomalies
from src.engine.cost_ingestor import create_demo_costs
from src.schemas.finops import DailyCostPoint


def test_demo_spikes_are_detected_with_decimal_findings() -> None:
    points = create_demo_costs(date(2025, 1, 30))

    findings = detect_anomalies(points)

    assert {(item.service_name, item.date) for item in findings} >= {
        ("Virtual Machines", date(2025, 1, 23)),
        ("Azure SQL Database", date(2025, 1, 26)),
    }
    assert all(isinstance(item.actual_cost, Decimal) for item in findings)
    assert all(item.delta_percentage is not None for item in findings)


def test_detector_rejects_duplicate_days_for_a_service() -> None:
    day = date(2025, 1, 1)
    points = [
        DailyCostPoint(
            date=day + timedelta(days=index),
            service_name="Compute",
            amount=Decimal("1"),
        )
        for index in range(7)
    ]
    points.append(points[-1])

    with pytest.raises(ValueError, match="Duplicate daily costs"):
        detect_anomalies(points)


def test_summary_rejects_mixed_currency_totals() -> None:
    points = [
        DailyCostPoint(
            date=date(2025, 1, 1), service_name="A", amount=Decimal("1"), currency="USD"
        ),
        DailyCostPoint(
            date=date(2025, 1, 1), service_name="B", amount=Decimal("1"), currency="EUR"
        ),
    ]

    with pytest.raises(ValueError, match="multiple currencies"):
        build_run_summary(points, [], source_mode="demo")
