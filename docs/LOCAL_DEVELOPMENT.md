# Local Development Guide

This guide covers running the FinOps Explainer API and React dashboard on Windows PowerShell. Use
the repository [README](../README.md) for architecture, decisions, API contracts, and the complete
configuration reference.

## Prerequisites

- Python 3.12
- Node.js 24+
- Azure Functions Core Tools v4
- Azurite for local Functions host storage (the timer trigger uses AzureWebJobsStorage)
- Azure CLI only when using live Cost Management data or Azure persistence

Check the installed tools:

```powershell
py -3.12 --version
node --version
npm --version
func --version
```

## 1. Create and configure the Python environment

From `C:\Projects\finops-explainer-app`:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -r requirements-dev.txt -r requirements-sec.txt
```

The PowerShell execution-policy change applies only to the current terminal process.

Create an untracked `local.settings.json` in the repository root for the local Functions host:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "MODE": "demo",
    "PERSISTENCE_MODE": "memory"
  }
}
```

Start Azurite in a separate terminal if it is not already running. The app itself uses the
deterministic demo fixture and in-memory persistence; Azurite is only for the Functions host's
storage and timer infrastructure.

## 2. Start the Azure Functions API

In the app root, with the virtual environment active:

```powershell
func start
```

The local API routes are:

- `http://127.0.0.1:7071/api/health`
- `http://127.0.0.1:7071/api/anomalies`
- `http://127.0.0.1:7071/api/runs`
- `http://127.0.0.1:7071/api/analyze`

The routes require Function-level authorization. Use a non-production local Function key generated
for the local Functions host, or a separately managed non-production Function App key. Do not put
the key in `local.settings.json`, `.env` files, source code, shell history, URLs, or Vite build
variables.

## 3. Start the React dashboard

In another terminal:

```powershell
Set-Location C:\Projects\finops-explainer-app\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the local Functions host on port 7071.
Paste the Function key into the dashboard's protected API connection panel. It stays in the tab's
React state only; refreshing or closing the tab clears it.

If the API is unreachable, the dashboard switches to a static, clearly labeled offline preview.
That fixture is in-memory only, is not persisted, and does not run anomaly calculations in the
browser. The **Run analysis** button is disabled in offline preview mode.

## 4. Optional live data and Azure persistence

For live Cost Management queries, sign in with an identity that has the required read permission:

```powershell
az login
$env:MODE = "live"
$env:AZURE_SUBSCRIPTION_ID = "<subscription-id>"
```

Optionally set `COST_MANAGEMENT_SCOPE` to the approved billing scope and `AZURE_CLIENT_ID` to select
the Phase 1 user-assigned application identity. Without `COST_MANAGEMENT_SCOPE`, the app queries the
subscription scope.

Azure persistence additionally needs:

```powershell
$env:PERSISTENCE_MODE = "azure"
$env:STORAGE_ACCOUNT_NAME = "<terraform-storage-account-output>"
$env:COSMOS_ACCOUNT_NAME = "<terraform-cosmos-account-output>"
```

The provisioned names default to Blob container `finops-anomalies`, Cosmos database `finops`, and
container `anomalies`. `TENANT_ID` selects the `/tenantId` partition and defaults to `default`.

**The current Phase 1 runtime identity is read-only for Blob and Cosmos.** It cannot persist app run
snapshots or anomaly records until the infra repository grants the required write-capable data
roles. Azure-mode write failures are reported; they do not silently become successful memory writes.
For local development without those roles, use `PERSISTENCE_MODE=memory`.

To try the optional Azure OpenAI narrator, configure `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_DEPLOYMENT`. Authentication uses `DefaultAzureCredential`; no API key is required or
accepted. If these settings are absent or the provider fails, the deterministic narrative template
is used and the UI displays its provider/fact-check status.

## 5. Run checks

From the app root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests function_app.py
.\.venv\Scripts\ruff.exe format --check src tests function_app.py
.\.venv\Scripts\mypy.exe src tests function_app.py
.\.venv\Scripts\bandit.exe -r src function_app.py -q
.\.venv\Scripts\pip-audit.exe -r requirements.txt
```

From `frontend`:

```powershell
npm ci
npm audit --audit-level=moderate
npm run lint
npm run build
```

## Local secret hygiene

- `local.settings.json`, `.env*`, `.npmrc`, private keys, and dependency/build directories are
  ignored by Git.
- Never name a Vite variable `VITE_FUNCTION_KEY` or otherwise embed a Function key in frontend
  configuration. `VITE_API_BASE_URL` is public and may contain only the API base URL.
- Before committing, inspect staged paths and confirm no local settings, keys, billing exports, or
  Terraform state files are included.
