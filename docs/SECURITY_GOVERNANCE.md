# Security and Governance

## Phase 1 infrastructure contract

This app targets the Phase 1 resources in `finops-explainer-infra`:

| App setting | Terraform source/output | Provisioned value |
| --- | --- | --- |
| `AZURE_SUBSCRIPTION_ID` | `subscription_id` / GitHub Actions variable `AZURE_SUBSCRIPTION_ID` | Selected subscription |
| `AZURE_CLIENT_ID` | `managed_identity_client_id` output | User-assigned app identity |
| `COST_MANAGEMENT_SCOPE` | `cost_management_scope` | Defaults to `/subscriptions/<subscription-id>` |
| `STORAGE_ACCOUNT_NAME` | `storage_account_name` output | Terraform-generated name |
| `STORAGE_CONTAINER_NAME` | `azurerm_storage_container.anomalies` | `finops-anomalies` |
| `COSMOS_ACCOUNT_NAME` | `cosmos_account_name` output | Terraform-generated name |
| `COSMOS_DATABASE_NAME` | `cosmos_database_name` output | `finops` |
| `COSMOS_CONTAINER_NAME` | `cosmos_container_name` output | `anomalies` |
| `MODE` | App setting | `demo` by default; `live` enables Cost Management |
| `PERSISTENCE_MODE` | App setting | `memory` for demo; `azure` for live by default |

Phase 1 does **not** provision a Storage Queue. Do not configure or depend on a queue unless
infrastructure is deliberately updated in a later phase. Phase 2 reads live costs directly from
the Cost Management Query API. The storage and Cosmos accounts use managed identity and have
key-based authentication disabled.

Phase 3 persistence uses `STORAGE_ACCOUNT_NAME` to connect to the `finops-anomalies` Blob container
and `COSMOS_ACCOUNT_NAME` to connect to the `finops` database and `anomalies` container. Optional
`STORAGE_CONTAINER_NAME`, `COSMOS_DATABASE_NAME`, and `COSMOS_CONTAINER_NAME` overrides default to
those provisioned names. `TENANT_ID` selects the Cosmos `/tenantId` partition and defaults to
`default` for a single-tenant portfolio deployment. `PERSISTENCE_MODE=memory` is intended for local
offline runs; Azure mode requires the configured resource names and managed identity.

**Write-permission prerequisite:** Phase 1 currently grants `Storage Blob Data Reader` and Cosmos DB
Built-in Data Reader, while Phase 3 writes run snapshots and anomaly documents. Azure persistence
therefore requires a deliberate least-privilege Phase 1/IaC role-assignment update to grant blob
write and Cosmos item write permissions (for example, `Storage Blob Data Contributor` and the
Cosmos DB Built-in Data Contributor data-plane role). Until that is applied, Azure-mode writes
return a sanitized error; the app does not silently report an in-memory write as a successful
durable save.

The managed identity has `Cost Management Reader`, `Storage Blob Data Reader`,
`Key Vault Secrets User`, and Cosmos DB Built-in Data Reader roles. The app must not request broader
permissions or use account keys. `DefaultAzureCredential` supports local Azure CLI sign-in and the
user-assigned managed identity in Azure. `AZURE_CLIENT_ID` selects the latter when configured.

## Functions API

- `GET /api/health` reports the selected mode and persistence backend.
- `GET /api/anomalies` returns recent anomaly records; optional query parameters are `limit`,
  `service`, and `severity`.
- `GET /api/runs` returns recent run summaries; `run_id` retrieves a single complete run.
- `POST /api/analyze` performs one analysis; the optional JSON body is `{"as_of":"YYYY-MM-DD"}`.
- A timer trigger runs analysis every six hours.

All HTTP routes use Function-level authorization and require a Function key, normally provided with
the `x-functions-key` header. HTTP errors expose only a safe message and correlation ID. Responses
carry correlation IDs; W3C `traceparent` IDs are included in structured JSON logs.

## Python and dependency controls

- Target Python 3.12 and install pinned runtime dependencies from `requirements.txt`.
- Keep development and security tools separately pinned in `requirements-dev.txt` and
  `requirements-sec.txt`.
- Exclude `.venv`, local settings, `.env`, keys, and build artifacts from source control.
- Review dependency updates with tests and `pip-audit`; run Bandit as part of security checks.

## Data and numerical governance

- Use deterministic Python `Decimal` arithmetic with `ROUND_HALF_UP` for costs, deltas,
  percentages, and Z-scores. Do not use an LLM for calculations.
- Only accept generated numerical narrative after `check_narrative` verifies every extracted
  number and percentage against the anomaly findings. Unsupported claims fail closed.
- Keep demo data synthetic. Do not log billing rows, raw Azure responses, tokens, or credential
  material.
- Return only sanitized errors to clients; internal exception payloads and credential-related
  details must not be copied into API responses.

## Identity, logging, and correlation

- Use the Phase 1 user-assigned managed identity in Azure and least-privilege role assignments.
- The optional narrator uses Azure OpenAI only when `AZURE_OPENAI_ENDPOINT` and
  `AZURE_OPENAI_DEPLOYMENT` are configured. It obtains an Entra token with the managed identity;
  no API key is accepted or stored. Without those settings, narrative generation uses a deterministic
  template. `AZURE_OPENAI_API_VERSION` optionally overrides the SDK's default API version.
- Emit structured JSON logs through `configure_json_logging`; wrap request handling in
  `correlation_context` so each log record has the request correlation ID.
- Treat user-provided correlation IDs as opaque identifiers. Do not use them to carry secrets or
  personally identifiable information.
- Do not log access tokens, connection strings, authorization headers, raw exception bodies, or
  unredacted user input. Preserve the correlation ID in client-safe error responses without
  exposing internal details.
