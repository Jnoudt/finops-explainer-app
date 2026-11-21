from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import HttpResponseError

from src.config import Settings
from src.engine import store as store_module
from src.engine.store import FinOpsStore
from src.schemas.finops import (
    AnomalyFinding,
    DashboardPayload,
    DailyCostPoint,
    RunSummary,
)

RUN_ID = "0123456789abcdef0123456789abcdef"


def _payload() -> DashboardPayload:
    point = DailyCostPoint(
        date=date(2025, 1, 1),
        service_name="Compute",
        amount=Decimal("120.00"),
    )
    finding = AnomalyFinding(
        date=point.date,
        service_name=point.service_name,
        actual_cost=Decimal("120.00"),
        baseline_cost=Decimal("60.00"),
        delta_amount=Decimal("60.00"),
        delta_percentage=Decimal("100.00"),
        z_score=Decimal("3.50"),
        severity="high",
        direction="increase",
    )
    return DashboardPayload(
        correlation_id="test",
        summary=RunSummary(
            start_date=point.date,
            end_date=point.date,
            total_cost=point.amount,
            point_count=1,
            service_count=1,
            anomaly_count=1,
            source_mode="demo",
        ),
        daily_costs=(point,),
        anomalies=(finding,),
    )


def test_memory_store_persists_and_queries_run_and_anomaly() -> None:
    store = FinOpsStore(Settings.from_environment({"MODE": "demo"}))
    payload = _payload()

    store.persist_run(RUN_ID, payload)

    run = store.get_run(RUN_ID)
    assert run is not None
    assert run["payload"]["summary"]["total_cost"] == "120.00"
    assert store.list_runs()[0]["run_id"] == RUN_ID
    anomalies = store.list_anomalies(service_name="compute", severity="high")
    assert len(anomalies) == 1
    assert anomalies[0]["run_id"] == RUN_ID


def test_memory_store_is_tenant_scoped_and_validates_run_ids() -> None:
    store = FinOpsStore(
        Settings.from_environment({"MODE": "demo"}), tenant_id="tenant-a"
    )
    store.persist_run(RUN_ID, _payload())
    other_tenant = FinOpsStore(
        Settings.from_environment({"MODE": "demo"}), tenant_id="tenant-b"
    )

    assert other_tenant.get_run(RUN_ID) is None
    assert other_tenant.list_runs() == []
    with pytest.raises(ValueError, match="32-character"):
        store.get_run("../invalid")
    with pytest.raises(ValueError, match="limit must be"):
        store.list_runs(501)


def test_azure_store_requires_provisioned_account_names() -> None:
    with pytest.raises(ValueError, match="STORAGE_ACCOUNT_NAME"):
        Settings.from_environment(
            {
                "MODE": "demo",
                "PERSISTENCE_MODE": "azure",
                "COSMOS_ACCOUNT_NAME": "cosmos-finops-test",
            }
        )


def test_azure_store_uses_phase_one_resources_and_partition_key(monkeypatch) -> None:
    settings = Settings.from_environment(
        {
            "MODE": "demo",
            "PERSISTENCE_MODE": "azure",
            "STORAGE_ACCOUNT_NAME": "stfinops123456",
            "COSMOS_ACCOUNT_NAME": "cosmos-finops-dev-123456",
            "AZURE_CLIENT_ID": "managed-identity-id",
        }
    )
    credential = MagicMock()
    blob_container = MagicMock()
    blob_service = MagicMock()
    blob_service.get_container_client.return_value = blob_container
    cosmos_container = MagicMock()
    cosmos_database = MagicMock()
    cosmos_database.get_container_client.return_value = cosmos_container
    cosmos_client = MagicMock()
    cosmos_client.get_database_client.return_value = cosmos_database
    monkeypatch.setattr(
        store_module, "DefaultAzureCredential", MagicMock(return_value=credential)
    )
    blob_factory = MagicMock(return_value=blob_service)
    cosmos_factory = MagicMock(return_value=cosmos_client)
    monkeypatch.setattr(store_module, "BlobServiceClient", blob_factory)
    monkeypatch.setattr(store_module, "CosmosClient", cosmos_factory)

    store = FinOpsStore(settings, tenant_id="tenant-a")
    store.persist_run(RUN_ID, _payload())

    blob_factory.assert_called_once_with(
        account_url="https://stfinops123456.blob.core.windows.net",
        credential=credential,
    )
    blob_service.get_container_client.assert_called_once_with("finops-anomalies")
    cosmos_factory.assert_called_once_with(
        "https://cosmos-finops-dev-123456.documents.azure.com:443/",
        credential=credential,
    )
    cosmos_client.get_database_client.assert_called_once_with("finops")
    cosmos_database.get_container_client.assert_called_once_with("anomalies")
    cosmos_container.upsert_item.assert_called_once()
    assert cosmos_container.upsert_item.call_args.args[0]["tenantId"] == "tenant-a"


def test_azure_write_error_propagates_without_memory_fallback(monkeypatch) -> None:
    settings = Settings.from_environment(
        {
            "MODE": "demo",
            "PERSISTENCE_MODE": "azure",
            "STORAGE_ACCOUNT_NAME": "stfinops123456",
            "COSMOS_ACCOUNT_NAME": "cosmos-finops-dev-123456",
        }
    )
    blob_container = MagicMock()
    blob_service = MagicMock()
    blob_service.get_container_client.return_value = blob_container
    blob_container.get_blob_client.return_value.upload_blob.side_effect = (
        HttpResponseError(message="write permission denied")
    )
    cosmos_client = MagicMock()
    cosmos_database = MagicMock()
    cosmos_client.get_database_client.return_value = cosmos_database
    monkeypatch.setattr(
        store_module, "DefaultAzureCredential", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        store_module, "BlobServiceClient", MagicMock(return_value=blob_service)
    )
    monkeypatch.setattr(
        store_module, "CosmosClient", MagicMock(return_value=cosmos_client)
    )
    store = FinOpsStore(settings)

    with pytest.raises(HttpResponseError, match="write permission denied"):
        store.persist_run(RUN_ID, _payload())

    assert store._runs == {}
