# GitHub Push and Deployment Guide

The app and infrastructure are separate repositories with separate histories and workflows. Push
each repository from its own working tree; do not put Terraform or infrastructure changes into the
app repository.

## 1. Confirm the repository checkouts

The expected local paths are:

- App: `C:\Projects\finops-explainer-app`
- Infrastructure: `C:\Projects\finops-explainer-infra`

In each directory, confirm Git is operating on the intended repository before staging:

```powershell
git rev-parse --show-toplevel
git remote -v
git status --short --branch
```

If these commands report that a directory is not a Git worktree or has no expected remote, stop and
clone/configure the correct GitHub repository before pushing. Do not initialize a new history over
an existing GitHub repository.

## 2. Configure OIDC repository variables

Configure these **repository variables** in GitHub Settings → Secrets and variables → Actions:

| Variable | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | GitHub Actions federated deployment principal |
| `AZURE_TENANT_ID` | Microsoft Entra tenant |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription |

No client secret is needed. The OIDC principal must have only the permissions required by its
workflow.

The same variable name can have different values in different contexts: the GitHub
`AZURE_CLIENT_ID` is the CI/CD deployment identity; the Azure Function App runtime setting
`AZURE_CLIENT_ID` selects the Phase 1 user-assigned application identity. Do not substitute one for
the other.

### Federated credentials

The app deployment job uses the GitHub environment `production`; configure its federated credential
subject for the app repository's `production` environment. The infra workflow uses `production` on
`main` and `validation` for other refs, so configure the corresponding subjects if those workflow
paths are used. Restrict each credential to the intended organization, repository, environment, and
audience.

## 3. Push and deploy infrastructure

Review the change and Terraform plan locally from the infrastructure working tree:

```powershell
Set-Location C:\Projects\finops-explainer-infra
terraform fmt -check -recursive
terraform init
terraform validate
.\check-iac.ps1
terraform plan -var-file="terraform.tfvars"
```

Keep `terraform.tfvars`, state, plans, credentials, and provider caches out of Git. Configure secured
remote Terraform state before using a workflow that could deploy shared or production resources.
Review the infrastructure repository's README and `tf-deploy.yml` for its state/backend settings.

Push the infrastructure repository on its own:

```powershell
git status --short
git add path\to\reviewed-infra-file.tf
git diff --cached --check
git diff --cached --name-only
git commit -m "Describe infrastructure change"
git push origin main
```

Replace the `git add` example path with only the files you reviewed; do not stage the entire
repository blindly.

The infra repository's `tf-deploy.yml` runs validation/plan on pull requests and pushes and applies
only on a push to `main`. Its `secops.yml` performs Terraform/Trivy checks; optional scanners require
their documented variables/secrets.

**Phase 1 does not provision an Azure Function App or frontend hosting resource.** The app deploy
job remains skipped until an appropriate Function App exists and deployment access is configured.
Phase 1 also grants read-only Blob and Cosmos data roles. Update its Terraform role assignments
deliberately before enabling durable writes; see [Security and Governance](./SECURITY_GOVERNANCE.md).

## 4. Push and deploy the app

Run local checks first:

```powershell
Set-Location C:\Projects\finops-explainer-app
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

Return to the app root and review exactly what is staged:

```powershell
Set-Location C:\Projects\finops-explainer-app
git status --short
git add path\to\reviewed-app-file.py
git diff --cached --check
git diff --cached --name-only
```

Replace the `git add` example path with only the files you reviewed; do not stage the entire
repository blindly.

Do not stage `.venv`, `frontend/node_modules`, `frontend/dist`, `.env` files, `local.settings.json`,
Function keys, private keys, billing exports, or generated secrets. The frontend key is entered in
the UI and is not part of the repository.

Commit and push the app independently:

```powershell
git commit -m "Describe app change"
git push origin main
```

The app `app-deploy.yml` workflow runs Python tests/quality/security plus frontend audit/lint/build
on pull requests and pushes to `main`. Its Azure Functions deployment job runs only for `main`
pushes or manual dispatch when `AZURE_FUNCTIONAPP_NAME` is configured.

Configure this additional **repository variable** only after the target Function App exists:

- `AZURE_FUNCTIONAPP_NAME` — existing Python/Linux Azure Function App name

The federated deployment identity needs permission to deploy code to that Function App. The workflow
deploys the Python Function App only; it does not create resources, change app settings/RBAC, or
deploy the React static site. Configure runtime settings on the Function App using the Terraform
outputs and app contract. Host the frontend separately, set its public `VITE_API_BASE_URL`, and allow
only the frontend's HTTPS origin in Function App CORS. Never place the Function key in a Vite
variable or static build.

## 5. Check workflow results

After each push, confirm the matching repository's Actions run completed successfully. For the app:

1. `quality` must pass before deployment can start.
2. `deploy-functions` is expected to be skipped until `AZURE_FUNCTIONAPP_NAME` and a target Function
   App are configured.
3. If deployment is enabled, verify the deployed app's runtime settings and managed identity
   permissions separately; the workflow deploys code only.

Do not copy credentials, Function keys, Terraform state, or raw billing data into Actions logs or
issue/PR comments.
