from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.config import Settings
from src.engine import narrator
from src.engine.narrator import generate_narrative
from src.schemas.finops import AnomalyFinding


def _finding() -> AnomalyFinding:
    return AnomalyFinding(
        date=date(2025, 1, 23),
        service_name="Virtual Machines",
        actual_cost=Decimal("156.40"),
        baseline_cost=Decimal("46.00"),
        delta_amount=Decimal("110.40"),
        delta_percentage=Decimal("240.00"),
        z_score=Decimal("4.25"),
        currency="USD",
        severity="high",
        direction="increase",
    )


def test_unconfigured_narrator_uses_grounded_deterministic_template(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)

    result = generate_narrative(
        [_finding()],
        correlation_id="test-run",
        settings=Settings.from_environment({"MODE": "demo"}),
    )

    assert result.narrative.provider == "deterministic_template"
    assert "240.00%" in result.narrative.text
    assert result.fact_check.accepted


def test_narrator_template_handles_empty_findings() -> None:
    result = generate_narrative(
        [],
        correlation_id="test-run",
        settings=Settings.from_environment({"MODE": "demo"}),
    )

    assert "No anomalies" in result.narrative.text
    assert result.fact_check.accepted
    assert result.fact_check.checked_claims == ()


def test_unsupported_model_narrative_falls_back_to_verified_template(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "narrator")
    credential = MagicMock()
    credential_factory = MagicMock(return_value=credential)
    monkeypatch.setattr(narrator, "DefaultAzureCredential", credential_factory)
    monkeypatch.setattr(
        narrator,
        "get_bearer_token_provider",
        MagicMock(return_value=lambda: "test-token"),
    )
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Costs rose 999%."))]
    )
    monkeypatch.setattr(narrator, "AzureOpenAI", MagicMock(return_value=client))

    result = generate_narrative(
        [_finding()],
        correlation_id="test-run",
        settings=Settings.from_environment({"MODE": "demo"}),
    )

    assert result.narrative.provider == "deterministic_template"
    assert "240.00%" in result.narrative.text
    assert result.fact_check.accepted
    client.close.assert_called_once()
    credential.close.assert_called_once()
