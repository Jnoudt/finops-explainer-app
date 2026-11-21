from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.config import Settings
from src.engine import cost_ingestor
from src.engine.cost_ingestor import create_demo_costs, load_costs


def test_demo_costs_are_repeatable_and_cover_four_services_for_thirty_days() -> None:
    as_of = date(2025, 1, 30)

    first_run = create_demo_costs(as_of)
    second_run = create_demo_costs(as_of)

    assert first_run == second_run
    assert len(first_run) == 120
    assert len({point.service_name for point in first_run}) == 4
    assert len({point.date for point in first_run}) == 30
    assert create_demo_costs() == first_run


def test_live_settings_use_subscription_scope_by_default() -> None:
    settings = Settings.from_environment(
        {
            "MODE": "live",
            "AZURE_SUBSCRIPTION_ID": "subscription-id",
            "PERSISTENCE_MODE": "memory",
        }
    )

    assert settings.cost_management_scope == "/subscriptions/subscription-id"
    assert load_costs(
        "demo", as_of=date(2025, 1, 30), settings=settings
    ) == create_demo_costs(date(2025, 1, 30))


def test_live_query_results_are_normalized_to_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        mode="live",
        persistence_mode="memory",
        subscription_id="subscription-id",
        cost_management_scope="/subscriptions/subscription-id",
        managed_identity_client_id="identity-client-id",
        storage_account_name=None,
        storage_container_name="finops-anomalies",
        cosmos_account_name=None,
        cosmos_database_name="finops",
        cosmos_container_name="anomalies",
    )
    result = SimpleNamespace(
        columns=[
            SimpleNamespace(name=name)
            for name in ("PreTaxCost", "UsageDate", "ServiceName", "Currency")
        ],
        rows=[[12.345, 20250130, "Compute", "USD"]],
    )
    credential = MagicMock()
    credential.__enter__.return_value = credential
    client = MagicMock()
    client.__enter__.return_value = client
    client.query.usage.return_value = result
    credential_factory = MagicMock(return_value=credential)
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(cost_ingestor, "DefaultAzureCredential", credential_factory)
    monkeypatch.setattr(cost_ingestor, "CostManagementClient", client_factory)

    points = load_costs("live", as_of=date(2025, 1, 30), settings=settings)

    assert points[0].amount == Decimal("12.35")
    assert points[0].date == date(2025, 1, 30)
    credential_factory.assert_called_once_with(
        managed_identity_client_id="identity-client-id"
    )
    client.query.usage.assert_called_once()
    assert client.query.usage.call_args.args[0] == settings.cost_management_scope
