# FinOps Explainer

An Azure FinOps anomaly explainer with a Python 3.12 Azure Functions v2 API and a React + TypeScript
dashboard. Phase 1 Terraform owns the Azure resources; this repository contains the app, deterministic
analysis engine, grounded narrative boundary, persistence adapters, and dashboard.

## Architecture

```text
React + TypeScript dashboard
    ├── Function-key-protected /api/health, /api/anomalies, /api/runs, /api/analyze
    └── Static in-memory offline preview when the API cannot be reached
                 │
                 ▼
Azure Functions v2 (Python 3.12)
    ├── Cost Management Query API via DefaultAzureCredential (MODE=live)
    ├── Stable 30-day, four-service synthetic fixture (MODE=demo)
    ├── Decimal rolling baseline, variance, and Z-score engine
    ├── Optional Azure OpenAI narrative → numerical fact checker → template fallback
    └── Blob run snapshots + Cosmos anomaly records (or local in-memory store)
                 │
                 ▼
Phase 1 FinOps resources
    ├── Storage container: finops-anomalies
    ├── Cosmos DB: finops / anomalies, partition key /tenantId
    └── User-assigned managed identity and least-privilege RBAC
```

## Operator guides

- [Local development and run instructions](./docs/LOCAL_DEVELOPMENT.md)
- [GitHub pushes, OIDC, and deployment instructions](./docs/GITHUB_DEPLOYMENT.md)

### Deterministic analysis and narrative boundary

All billing ingestion normalization, rolling baselines, deltas, percentages, Z-scores, and
run-level totals are computed in Python with `Decimal`, `ROUND_HALF_UP`, and `statistics`. The UI
formats API-provided numeric strings for display; it does not calculate financial metrics.

The optional Azure OpenAI narrator receives verified anomaly records only. Its response is accepted
only when `fact_checker.py` validates every extracted numeric figure and percentage against those
records. If the provider is not configured, throttles, errors, or produces an unsupported number,
the app uses a deterministic narrative template. The dashboard identifies the provider and shows
the fact-check verdict and unsupported-claim count.

### Schedule and API

The Functions timer runs at `0 0 */6 * * *` (every six hours). HTTP routes use Function-level
authorization:

| Route | Behavior |
| --- | --- |
| `GET /api/health` | Reports data mode and persistence backend |
| `GET /api/anomalies?limit=100&service=...&severity=...` | Lists recent anomaly findings |
| `GET /api/runs?limit=25` | Lists recent run summaries |
| `GET /api/runs?run_id=<32-character-id>` | Returns a complete run payload |
| `POST /api/analyze` | Runs analysis now; accepts optional `{"as_of":"YYYY-MM-DD"}` |

The frontend sends the Function key in the `x-functions-key` header. The key is held only in React
tab memory; it is not written to local/session storage, URLs, source files, or Vite build variables.

## Phase 1 resource contract and RBAC

The app uses the Phase 1 names: private Blob container `finops-anomalies`, Cosmos database `finops`,
and Cosmos container `anomalies`. `STORAGE_ACCOUNT_NAME` and `COSMOS_ACCOUNT_NAME` are the generated
account names from Terraform outputs. Optional overrides default to the provisioned container,
database, and container names. There is no Phase 1 queue; this app does not depend on one.

**Durable Azure writes require an IaC RBAC change.** Phase 1 currently grants the app identity
`Storage Blob Data Reader` and Cosmos DB Built-in Data Reader. Phase 3 writes run blobs and anomaly
documents, so Azure persistence requires write-capable least-privilege roles, such as `Storage Blob
Data Contributor` and Cosmos DB Built-in Data Contributor. Until the role assignments are updated,
Azure write failures are returned as sanitized errors; the app never claims that an in-memory write
was durably persisted.

The Phase 1 Terraform shown in the companion repository does not provision an Azure Function App.
The deployment workflow below stays skipped until `AZURE_FUNCTIONAPP_NAME` is configured and an
appropriate Function App and OIDC deployment role exist.

## Local setup

Prerequisites:

- Python 3.12
- Node.js 24 or newer compatible with the pinned Vite toolchain
- Azure Functions Core Tools v4
- Azurite if the local Functions host requires the AzureWebJobsStorage emulator

### Backend

From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -r requirements-sec.txt
```

Start the local Functions host in a backend terminal:

```powershell
func start
```

The default app settings are `MODE=demo` and `PERSISTENCE_MODE=memory`. For live Cost Management
queries, sign in with `az login` and set `MODE=live`, `AZURE_SUBSCRIPTION_ID`, and optionally
`COST_MANAGEMENT_SCOPE` and `AZURE_CLIENT_ID`. To select Azure persistence, set
`PERSISTENCE_MODE=azure`, `STORAGE_ACCOUNT_NAME`, and `COSMOS_ACCOUNT_NAME`; the local identity must
have the required read/write data-plane roles. Keep local host settings in the ignored
`local.settings.json`, never in source control.

### Frontend

In another PowerShell terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:7071`. Paste a local Functions key into the protected API
connection panel; it remains in that tab's memory and is cleared by the **Clear key** action. If the
API is unreachable, the UI presents a static, clearly labeled in-memory demo preview. It is not
stored and its Analyze button is disabled. `VITE_API_BASE_URL` can set the public API base URL at
build time; it must never contain a Function key.

## Configuration reference

| Setting | Default | Purpose |
| --- | --- | --- |
| `MODE` | `demo` | `demo` fixture or `live` Cost Management |
| `PERSISTENCE_MODE` | `memory` for demo, `azure` for live | Run/anomaly store |
| `AZURE_SUBSCRIPTION_ID` | — | Required in live mode |
| `COST_MANAGEMENT_SCOPE` | Subscription scope | Optional Cost Management scope |
| `AZURE_CLIENT_ID` | — | User-assigned managed identity client ID |
| `STORAGE_ACCOUNT_NAME` | — | Terraform-generated storage account for Azure persistence |
| `STORAGE_CONTAINER_NAME` | `finops-anomalies` | Provisioned private Blob container |
| `COSMOS_ACCOUNT_NAME` | — | Terraform-generated Cosmos account |
| `COSMOS_DATABASE_NAME` | `finops` | Provisioned SQL database |
| `COSMOS_CONTAINER_NAME` | `anomalies` | Provisioned anomaly container |
| `TENANT_ID` | `default` | Cosmos `/tenantId` partition |
| `AZURE_OPENAI_ENDPOINT` | — | Optional Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | — | Optional deployment name; both narrator settings enable LLM use |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Optional Azure OpenAI API version |
| `VITE_API_BASE_URL` | `/api` | Public frontend API base URL; no credentials |

`AZURE_CLIENT_ID` has different values in different contexts: the GitHub Actions repository variable
identifies the OIDC deployment principal, while the Function App's runtime setting selects the
Phase 1 user-assigned application identity.

## CI/CD and deployment

`.github/workflows/app-deploy.yml` runs Python 3.12 tests, Ruff, mypy, Bandit, pip-audit, frontend
dependency audit, lint, and build on pull requests and pushes to `main`. Deployment is conditional
on a `main` push or manual dispatch and a configured `AZURE_FUNCTIONAPP_NAME`.

Configure these GitHub **repository variables** for OIDC:

- `AZURE_CLIENT_ID` — federated deployment principal client ID
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_FUNCTIONAPP_NAME` — existing Python/Linux Function App

The deployment identity needs OIDC federation and permission to deploy code to the Function App.
The workflow deploys the Python Function App only; it does not deploy the React static site or
change app settings/RBAC. Configure Function App runtime settings and a separate static frontend
hosting target as appropriate for the environment. Frontend static hosting should use an HTTPS API
base URL and must not embed Function keys.

## ADRs

1. **Keep financial calculations in Python.** `Decimal` and the deterministic detector are the only
   source of financial figures; the browser renders the API response without recalculating it.
2. **Fail closed on narrative figures.** Azure OpenAI is optional and cannot override the verified
   anomaly table. Any unsupported extracted claim selects the deterministic template instead.
3. **Separate local convenience from cloud persistence.** Demo mode uses an explicitly labeled
   in-memory backend. Azure mode uses managed identity and surfaces authorization errors instead of
   silently downgrading writes.
4. **Keep Function keys ephemeral.** The UI holds the key in component memory and sends it only in
   the request header; no persistence or build-time injection is provided.
5. **Keep infrastructure outside the app deployment.** Terraform owns Azure resources and RBAC;
   the app workflow deploys only code after the Function App is provisioned.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests function_app.py
.\.venv\Scripts\ruff.exe format --check src tests function_app.py
.\.venv\Scripts\mypy.exe src tests function_app.py
.\.venv\Scripts\bandit.exe -r src function_app.py -q
.\.venv\Scripts\pip-audit.exe -r requirements.txt
Set-Location frontend
npm ci
npm audit --audit-level=moderate
npm run lint
npm run build
```
