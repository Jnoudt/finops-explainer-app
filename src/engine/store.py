"""Run and anomaly persistence in Azure Blob Storage and Cosmos DB."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient
from azure.core.exceptions import ResourceNotFoundError as BlobNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from src.config import Settings
from src.schemas.finops import DashboardPayload

_RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_MAX_LIMIT = 500


class FinOpsStore:
    """Persist run snapshots to blobs and anomaly records to Cosmos DB."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        tenant_id: str | None = None,
    ) -> None:
        self.settings = settings or Settings.from_environment()
        self.tenant_id = (
            tenant_id or os.environ.get("TENANT_ID", "").strip() or "default"
        )
        self._lock = threading.RLock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._credential: DefaultAzureCredential | None = None
        self._blob_container: Any = None
        self._cosmos_container: Any = None

        if self.settings.persistence_mode == "azure":
            self._initialize_azure_clients()

    def persist_run(self, run_id: str, payload: DashboardPayload) -> None:
        """Store a complete run snapshot and its anomaly documents."""
        self._validate_run_id(run_id)
        document = {
            "run_id": run_id,
            "tenantId": self.tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload.model_dump(mode="json"),
        }

        if self.settings.persistence_mode == "memory":
            with self._lock:
                self._runs[run_id] = document
            return

        blob_client = self._blob_container.get_blob_client(f"runs/{run_id}.json")
        blob_client.upload_blob(
            json.dumps(document, separators=(",", ":")), overwrite=True
        )
        for index, finding in enumerate(payload.anomalies):
            anomaly_document = {
                "id": f"{run_id}-{index}",
                "tenantId": self.tenant_id,
                "run_id": run_id,
                **finding.model_dump(mode="json"),
            }
            self._cosmos_container.upsert_item(anomaly_document)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        self._validate_run_id(run_id)
        if self.settings.persistence_mode == "memory":
            with self._lock:
                return self._runs.get(run_id)

        try:
            content = (
                self._blob_container.get_blob_client(f"runs/{run_id}.json")
                .download_blob()
                .readall()
            )
        except BlobNotFoundError:
            return None
        document = json.loads(content)
        if document.get("tenantId") != self.tenant_id:
            return None
        return document

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = self._validate_limit(limit)
        documents: list[dict[str, Any]]
        if self.settings.persistence_mode == "memory":
            with self._lock:
                documents = [
                    document
                    for document in self._runs.values()
                    if document["tenantId"] == self.tenant_id
                ]
            documents.sort(key=lambda item: item["created_at"], reverse=True)
            return [
                self._run_summary(document) for document in documents[:bounded_limit]
            ]

        blobs = self._blob_container.list_blobs(name_starts_with="runs/")
        documents = []
        for blob in blobs:
            if not blob.name.endswith(".json"):
                continue
            try:
                document = json.loads(
                    self._blob_container.get_blob_client(blob.name)
                    .download_blob()
                    .readall()
                )
            except BlobNotFoundError:
                continue
            if document.get("tenantId") == self.tenant_id:
                documents.append(document)
        documents.sort(key=lambda item: item["created_at"], reverse=True)
        return [self._run_summary(document) for document in documents[:bounded_limit]]

    def list_anomalies(
        self,
        limit: int = 100,
        *,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        bounded_limit = self._validate_limit(limit)
        if self.settings.persistence_mode == "memory":
            with self._lock:
                documents = [
                    {
                        "id": f"{run_id}-{index}",
                        "tenantId": document["tenantId"],
                        "run_id": run_id,
                        **finding,
                    }
                    for run_id, document in self._runs.items()
                    if document["tenantId"] == self.tenant_id
                    for index, finding in enumerate(document["payload"]["anomalies"])
                ]
            if service_name:
                documents = [
                    item
                    for item in documents
                    if item["service_name"].casefold() == service_name.casefold()
                ]
            if severity:
                documents = [item for item in documents if item["severity"] == severity]
            documents.sort(
                key=lambda item: (item["date"], item["service_name"]), reverse=True
            )
            return documents[:bounded_limit]

        parameters = [
            {"name": "@tenantId", "value": self.tenant_id},
            {"name": "@limit", "value": bounded_limit},
            {"name": "@serviceName", "value": service_name or ""},
            {"name": "@severity", "value": severity or ""},
        ]
        return list(
            self._cosmos_container.query_items(
                query=(
                    "SELECT TOP @limit * FROM c WHERE c.tenantId = @tenantId "
                    "AND (@serviceName = '' OR "
                    "LOWER(c.service_name) = LOWER(@serviceName)) "
                    "AND (@severity = '' OR c.severity = @severity) "
                    "ORDER BY c.date DESC"
                ),
                parameters=parameters,
                partition_key=self.tenant_id,
                max_item_count=bounded_limit,
            )
        )

    def _initialize_azure_clients(self) -> None:
        account_name = self.settings.storage_account_name
        cosmos_name = self.settings.cosmos_account_name
        if account_name is None or cosmos_name is None:
            raise ValueError("Azure persistence settings are incomplete.")

        self._credential = DefaultAzureCredential(
            managed_identity_client_id=self.settings.managed_identity_client_id
        )
        blob_service = BlobServiceClient(
            account_url=f"https://{account_name}.blob.core.windows.net",
            credential=self._credential,
        )
        self._blob_container = blob_service.get_container_client(
            self.settings.storage_container_name
        )
        cosmos_client = CosmosClient(
            f"https://{cosmos_name}.documents.azure.com:443/",
            credential=self._credential,
        )
        self._cosmos_container = cosmos_client.get_database_client(
            self.settings.cosmos_database_name
        ).get_container_client(self.settings.cosmos_container_name)

    @staticmethod
    def _run_summary(document: dict[str, Any]) -> dict[str, Any]:
        payload = document["payload"]
        return {
            "run_id": document["run_id"],
            "created_at": document["created_at"],
            "summary": payload["summary"],
            "anomaly_count": len(payload["anomalies"]),
        }

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not 1 <= limit <= _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}.")
        return limit

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("run_id must be a 32-character hexadecimal identifier.")
