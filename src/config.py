"""Runtime settings using the names and defaults from the Phase 1 Terraform."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Mapping

Mode = Literal["demo", "live"]
PersistenceMode = Literal["memory", "azure"]


@dataclass(frozen=True)
class Settings:
    mode: Mode
    persistence_mode: PersistenceMode
    subscription_id: str | None
    cost_management_scope: str | None
    managed_identity_client_id: str | None
    storage_account_name: str | None
    storage_container_name: str
    cosmos_account_name: str | None
    cosmos_database_name: str
    cosmos_container_name: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        raw_mode = values.get("MODE", "demo").strip().lower()
        if raw_mode == "demo":
            mode: Mode = "demo"
        elif raw_mode == "live":
            mode = "live"
        else:
            raise ValueError("MODE must be either 'demo' or 'live'.")

        raw_persistence = (
            values.get("PERSISTENCE_MODE", "memory" if mode == "demo" else "azure")
            .strip()
            .lower()
        )
        if raw_persistence == "memory":
            persistence_mode: PersistenceMode = "memory"
        elif raw_persistence == "azure":
            persistence_mode = "azure"
        else:
            raise ValueError("PERSISTENCE_MODE must be either 'memory' or 'azure'.")

        subscription_id = values.get("AZURE_SUBSCRIPTION_ID", "").strip() or None
        scope = values.get("COST_MANAGEMENT_SCOPE", "").strip() or None
        managed_identity_client_id = values.get("AZURE_CLIENT_ID", "").strip() or None
        storage_account_name = values.get("STORAGE_ACCOUNT_NAME", "").strip() or None
        cosmos_account_name = values.get("COSMOS_ACCOUNT_NAME", "").strip() or None

        if mode == "live":
            if subscription_id is None:
                raise ValueError("AZURE_SUBSCRIPTION_ID is required when MODE=live.")
            if scope is None:
                scope = f"/subscriptions/{subscription_id}"

        if persistence_mode == "azure":
            if storage_account_name is None:
                raise ValueError(
                    "STORAGE_ACCOUNT_NAME is required when PERSISTENCE_MODE=azure."
                )
            if cosmos_account_name is None:
                raise ValueError(
                    "COSMOS_ACCOUNT_NAME is required when PERSISTENCE_MODE=azure."
                )

        return cls(
            mode=mode,
            persistence_mode=persistence_mode,
            subscription_id=subscription_id,
            cost_management_scope=scope,
            managed_identity_client_id=managed_identity_client_id,
            storage_account_name=storage_account_name,
            storage_container_name=values.get(
                "STORAGE_CONTAINER_NAME", "finops-anomalies"
            ).strip(),
            cosmos_account_name=cosmos_account_name,
            cosmos_database_name=values.get("COSMOS_DATABASE_NAME", "finops").strip(),
            cosmos_container_name=values.get(
                "COSMOS_CONTAINER_NAME", "anomalies"
            ).strip(),
        )
