from datetime import date
from decimal import Decimal

from src.engine.fact_checker import check_narrative
from src.schemas.finops import AnomalyFinding


def _finding() -> AnomalyFinding:
    return AnomalyFinding(
        date=date(2025, 1, 30),
        service_name="Virtual Machines",
        actual_cost=Decimal("100.00"),
        baseline_cost=Decimal("50.00"),
        delta_amount=Decimal("50.00"),
        delta_percentage=Decimal("100.00"),
        z_score=Decimal("4.25"),
        currency="USD",
        severity="high",
        direction="increase",
    )


def test_fact_checker_accepts_grounded_values_and_ignores_dates() -> None:
    verdict = check_narrative(
        "On 2025-01-30, Virtual Machines cost $100.00, up 100.00% "
        "from a $50.00 baseline (z-score 4.25).",
        [_finding()],
    )

    assert verdict.accepted
    assert verdict.unsupported_claims == ()


def test_fact_checker_rejects_any_unsupported_number_or_percentage() -> None:
    verdict = check_narrative("Costs reached $100.00 and rose 125%.", [_finding()])

    assert not verdict.accepted
    assert verdict.unsupported_claims == ("125%",)
