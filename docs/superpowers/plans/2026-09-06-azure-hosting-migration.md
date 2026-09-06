# Azure Hosting Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move F1_Predictor and PL_Predictor off Render onto Azure Container Apps, and `predictor-hub` onto an Azure Static Web App, with zero behavior change to either app (PL_Predictor keeps its existing snapshot-serving mode as-is — converting it to live compute is a separate, follow-up plan).

**Architecture:** One Azure Resource Group holds a single Container Apps Environment shared by two Container Apps (`f1-predictor`, `pl-predictor`, Consumption plan, scale-to-zero) plus one Static Web App (the hub). Each backend repo gets its own GitHub Actions workflow: build the existing Dockerfile, push to GitHub Container Registry (public, no auth needed to pull), then update the Container App to the new image via `az containerapp update`, authenticated with an OIDC federated credential (no long-lived secret). The hub's Static Web App gets its own auto-deploy wired up natively at creation time.

**Tech Stack:** Azure CLI (`az`), Azure Container Apps, Azure Static Web Apps, GitHub Actions, GitHub Container Registry (GHCR), Docker (existing Dockerfiles, unchanged).

**Spec:** `docs/superpowers/specs/2026-09-06-azure-hosting-migration-design.md`

## Global Constraints

- Resource group: `predictor-hub-rg`
- Azure region: `eastus2` (widely available on Azure for Students, low latency to the apps' current Render US region)
- Container Apps Environment: `predictor-hub-env`
- Container App names: `f1-predictor`, `pl-predictor`
- Static Web App name: `predictor-hub`
- GHCR image names: `ghcr.io/kevocado/f1-predictor`, `ghcr.io/kevocado/pl-predictor` — **all lowercase** (GHCR rejects uppercase repo/package names; note the GitHub *repos* themselves are `F1_Predictor`/`PL_Predictor`, mixed case — only the *image* name must be lowercase)
- Both apps' only required runtime env var on Azure: `PUBLIC_MODE=true` (confirmed by reading both `config.py` files — every other env var either has a working default or is only needed by PL_Predictor's local snapshot-generation step, not the running container)
- Both apps listen on container port `8000` (confirmed in both Dockerfiles: `EXPOSE 8000` / `--port ${PORT:-8000}`) — Container Apps' `--target-port` must be `8000` for both; do not rely on Azure setting a `PORT` env var, it doesn't
- PL_Predictor's password gate is **already removed** from the codebase (commit `3691a35`, confirmed via `git log`) — do not add one back, and do not treat the Dockerfile's stale "GuestAuthMiddleware" comment as current behavior
- PL_Predictor's `refresh-public-snapshot.yml` GitHub Action **stays running** after this migration — Azure's PL_Predictor deployment still serves from the snapshot exactly like Render did, so this Action remains a live dependency, not something to retire as part of "decommissioning Render." (Retiring it is in scope for the separate follow-up plan that converts PL_Predictor to live compute.)
- Do not create Azure Container Registry (ACR) — GHCR (free, already in use via GitHub) is the registry for this plan
- This plan requires interactive steps only the user can perform (browser-based `az login`, approving an Azure AD app registration if prompted) — tasks say explicitly when to hand off
- Task 4/5's manual first-push step needs Docker running locally (`docker --version` should print something before starting either task; install Docker Desktop first if not)

---

### Task 1: Install and authenticate the Azure CLI

**Files:** none (local tooling setup)

**Interfaces:** none — this task just gets `az` working and logged into the right subscription for every later task to use.

- [ ] **Step 1: Install the Azure CLI**

```bash
brew update && brew install azure-cli
```

- [ ] **Step 2: Verify the install**

Run: `az --version`
Expected: prints a version number (e.g. `azure-cli   2.6x.x`) with no error.

- [ ] **Step 3: Log in (hand off to the user)**

Run: `az login`
This opens a browser for interactive sign-in — **the user must do this step themselves**, using their Azure for Students account. Wait for it to print a JSON list of subscriptions before continuing.

- [ ] **Step 4: Confirm the right subscription is active**

Run: `az account show --output table`
Expected: `IsDefault` is `True` for the Azure for Students subscription. If the wrong subscription is active (e.g. the user has more than one), run `az account set --subscription "<name-or-id>"` using a name/id from `az account list --output table`.

- [ ] **Step 5: Register the two resource providers this plan needs**

Run:
```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```
These are idempotent and safe to re-run. Confirm both finished with:
```bash
az provider show --namespace Microsoft.App --query registrationState --output tsv
az provider show --namespace Microsoft.OperationalInsights --query registrationState --output tsv
```
Expected: both print `Registered` (may take a minute after the register command; re-run the `show` command until it does).

---

### Task 2: Create the resource group and Container Apps Environment

**Files:** none

**Interfaces:**
- Produces: an Azure resource group `predictor-hub-rg` and a Container Apps Environment `predictor-hub-env` inside it, in region `eastus2` — every later Container App task targets these by name.

- [ ] **Step 1: Create the resource group**

```bash
az group create --name predictor-hub-rg --location eastus2
```
Expected: JSON output with `"provisioningState": "Succeeded"`.

- [ ] **Step 2: Create the Container Apps Environment**

```bash
az containerapp env create \
  --name predictor-hub-env \
  --resource-group predictor-hub-rg \
  --location eastus2
```
This takes a few minutes (it provisions a Log Analytics workspace alongside the environment). Expected: JSON output ending with `"provisioningState": "Succeeded"`.

- [ ] **Step 3: Verify it exists**

Run: `az containerapp env show --name predictor-hub-env --resource-group predictor-hub-rg --output table`
Expected: a table row showing `predictor-hub-env` in `eastus2` with provisioning state `Succeeded`.

---

### Task 3: Set up OIDC so GitHub Actions can deploy to Azure without a stored secret

**Files:** none (Azure AD + GitHub repo secrets)

**Interfaces:**
- Produces: three GitHub Actions repo secrets — `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` — that Task 4 and Task 5's workflows both authenticate with via `azure/login@v2`.

**Note:** Azure AD app registration is occasionally locked down on education/student tenants. If Step 2 below fails with a permissions error, fall back to Step 2b (a service-principal client secret instead of OIDC) — less ideal (a real secret to store and eventually rotate) but functionally equivalent and simpler to unblock.

- [ ] **Step 1: Create an Azure AD app registration + service principal, scoped to just this resource group**

```bash
az ad sp create-for-rbac \
  --name "predictor-hub-deploy" \
  --role contributor \
  --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/predictor-hub-rg \
  --query "{clientId:appId, tenantId:tenant}" \
  --output json
```
Expected: JSON with `clientId` and `tenantId`. Save both values — Step 4 needs them.

- [ ] **Step 2: Add a federated credential for each repo that will deploy (F1_Predictor and PL_Predictor)**

Replace `<CLIENT_ID>` with the `clientId` from Step 1. Run once per repo:

```bash
az ad app federated-credential create \
  --id <CLIENT_ID> \
  --parameters '{
    "name": "f1-predictor-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:Kevocado/F1_Predictor:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'

az ad app federated-credential create \
  --id <CLIENT_ID> \
  --parameters '{
    "name": "pl-predictor-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:Kevocado/PL_Predictor:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```
Expected: both print JSON with the new federated credential's `name`. If either command fails with a 403/permission error, **this is the tenant-lockdown case** — use Step 2b instead and skip straight to Step 3.

- [ ] **Step 2b (fallback only, skip if Step 2 succeeded): client-secret service principal instead of OIDC**

```bash
az ad sp create-for-rbac \
  --name "predictor-hub-deploy" \
  --role contributor \
  --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/predictor-hub-rg \
  --output json
```
This prints `appId`, `password`, and `tenant` — save all three. Task 4 and Task 5's workflows will use `azure/login@v2` with `creds: ${{ secrets.AZURE_CREDENTIALS }}` (a single JSON secret containing all three fields) instead of the three separate OIDC secrets — note this difference when you reach those tasks.

- [ ] **Step 3: Add the GitHub repo secrets (one-time, per repo)**

For **both** `Kevocado/F1_Predictor` and `Kevocado/PL_Predictor`, using the GitHub web UI (Settings → Secrets and variables → Actions → New repository secret) or the `gh` CLI:

```bash
gh secret set AZURE_CLIENT_ID --repo Kevocado/F1_Predictor --body "<clientId from Step 1>"
gh secret set AZURE_TENANT_ID --repo Kevocado/F1_Predictor --body "<tenantId from Step 1>"
gh secret set AZURE_SUBSCRIPTION_ID --repo Kevocado/F1_Predictor --body "$(az account show --query id -o tsv)"

gh secret set AZURE_CLIENT_ID --repo Kevocado/PL_Predictor --body "<clientId from Step 1>"
gh secret set AZURE_TENANT_ID --repo Kevocado/PL_Predictor --body "<tenantId from Step 1>"
gh secret set AZURE_SUBSCRIPTION_ID --repo Kevocado/PL_Predictor --body "$(az account show --query id -o tsv)"
```
(If Step 2b's fallback was used instead, set a single `AZURE_CREDENTIALS` secret per repo with the JSON `{"clientId":..., "clientSecret":..., "tenantId":..., "subscriptionId":...}` instead of the three above.)

- [ ] **Step 4: Verify the secrets landed**

Run: `gh secret list --repo Kevocado/F1_Predictor` and `gh secret list --repo Kevocado/PL_Predictor`
Expected: both list `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (or `AZURE_CREDENTIALS` if using the fallback).

---

### Task 4: Deploy F1_Predictor to Azure Container Apps

**Files:**
- Create: `F1_Predictor/.github/workflows/deploy-azure.yml`

**Interfaces:**
- Consumes: the `predictor-hub-env` Container Apps Environment (Task 2), the OIDC secrets (Task 3).
- Produces: a running Container App `f1-predictor` in `predictor-hub-rg`, reachable at `https://f1-predictor.<random>.eastus2.azurecontainerapps.io` (the exact hostname is printed by `az containerapp show` in Step 5) — Task 6 (hub link update) consumes this URL.

- [ ] **Step 1: First manual deploy, to create the Container App before CI takes over**

Build and push the image once by hand (proves the Dockerfile/GHCR path works before wiring CI to it):

```bash
cd F1_Predictor
docker build -t ghcr.io/kevocado/f1-predictor:latest .
echo $GITHUB_TOKEN | docker login ghcr.io -u Kevocado --password-stdin
docker push ghcr.io/kevocado/f1-predictor:latest
```
(`$GITHUB_TOKEN` here is a GitHub personal access token with `write:packages` scope — create one at github.com/settings/tokens if you don't have one, and export it in your shell first: `export GITHUB_TOKEN=ghp_...`.)

- [ ] **Step 2: Make the GHCR package public**

By default a newly-pushed GHCR image is private. Go to `https://github.com/users/Kevocado/packages/container/f1-predictor/settings`, scroll to "Danger Zone," and change visibility to Public. This lets Azure pull it without any registry credentials at all.

- [ ] **Step 3: Create the Container App**

```bash
az containerapp create \
  --name f1-predictor \
  --resource-group predictor-hub-rg \
  --environment predictor-hub-env \
  --image ghcr.io/kevocado/f1-predictor:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars PUBLIC_MODE=true
```
Expected: JSON output ending `"provisioningState": "Succeeded"`, and a `properties.configuration.ingress.fqdn` field with the app's public hostname.

- [ ] **Step 4: Verify it serves correctly**

```bash
FQDN=$(az containerapp show --name f1-predictor --resource-group predictor-hub-rg --query properties.configuration.ingress.fqdn -o tsv)
curl -s -o /dev/null -w "%{http_code}\n" "https://$FQDN/"
curl -s "https://$FQDN/api/races/2026/1/predictions" | head -c 300
```
Expected: the first command prints `200`; the second returns real JSON (not an error page). If the second command 404s because the season/round numbers are wrong, that's fine — the point is confirming the API responds at all, not that specific data exists. Also time a second request to confirm the scale-to-zero wake-up behavior is tolerable:
```bash
time curl -s -o /dev/null "https://$FQDN/"
```
Expected: well under 30 seconds even cold (F1's models load at startup — this is the number to sanity-check against the spec's "2-10s for small containers" estimate, since F1's containers aren't small).

- [ ] **Step 5: Write the CI workflow for future pushes**

Create `F1_Predictor/.github/workflows/deploy-azure.yml`:

```yaml
name: Deploy to Azure Container Apps

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read
  packages: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        run: |
          docker build -t ghcr.io/kevocado/f1-predictor:${{ github.sha }} -t ghcr.io/kevocado/f1-predictor:latest .
          docker push ghcr.io/kevocado/f1-predictor:${{ github.sha }}
          docker push ghcr.io/kevocado/f1-predictor:latest

      - name: Log in to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy new image to Container App
        run: |
          az containerapp update \
            --name f1-predictor \
            --resource-group predictor-hub-rg \
            --image ghcr.io/kevocado/f1-predictor:${{ github.sha }}
```
(If Task 3 used the client-secret fallback instead of OIDC, replace the `azure/login@v2` step's `with:` block with `creds: ${{ secrets.AZURE_CREDENTIALS }}` and drop the `id-token: write` permission — it's only needed for OIDC.)

Tagging by commit SHA (not just `latest`) means `az containerapp update --image ...:<sha>` always deploys the exact commit that built it, not whatever `latest` happens to point to at the moment Azure pulls — avoids a race if two pushes land close together.

- [ ] **Step 6: Commit and verify CI picks it up**

```bash
cd F1_Predictor
git add .github/workflows/deploy-azure.yml
git commit -m "ci: deploy to Azure Container Apps on push to main"
git push
```
Then watch it run: `gh run watch --repo Kevocado/F1_Predictor` (or check the Actions tab on github.com). Expected: the workflow completes green. Confirm the deployed revision changed:
```bash
az containerapp revision list --name f1-predictor --resource-group predictor-hub-rg --output table
```
Expected: a new revision at the top of the list, created just now.

---

### Task 5: Deploy PL_Predictor to Azure Container Apps

**Files:**
- Create: `PL_Predictor/.github/workflows/deploy-azure.yml`

**Interfaces:**
- Consumes: the `predictor-hub-env` Container Apps Environment (Task 2), the OIDC secrets (Task 3).
- Produces: a running Container App `pl-predictor` in `predictor-hub-rg` — same snapshot-serving behavior it has on Render today. Task 6 consumes its URL.

This is Task 4's exact structure, repeated for PL_Predictor — same reasoning, same fallback notes, not re-explained here.

- [ ] **Step 1: First manual build, push, and make public**

```bash
cd Prem_Predictor/PL_Predictor
docker build -t ghcr.io/kevocado/pl-predictor:latest .
echo $GITHUB_TOKEN | docker login ghcr.io -u Kevocado --password-stdin
docker push ghcr.io/kevocado/pl-predictor:latest
```
Then make it public at `https://github.com/users/Kevocado/packages/container/pl-predictor/settings` (Danger Zone → visibility → Public).

- [ ] **Step 2: Create the Container App**

```bash
az containerapp create \
  --name pl-predictor \
  --resource-group predictor-hub-rg \
  --environment predictor-hub-env \
  --image ghcr.io/kevocado/pl-predictor:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars PUBLIC_MODE=true
```

- [ ] **Step 3: Verify it serves correctly, including the snapshot path**

```bash
FQDN=$(az containerapp show --name pl-predictor --resource-group predictor-hub-rg --query properties.configuration.ingress.fqdn -o tsv)
curl -s -o /dev/null -w "%{http_code}\n" "https://$FQDN/"
curl -s "https://$FQDN/api/fixtures/gameweek" | python3 -m json.tool | head -20
```
Expected: `200`, and the second command returns real fixture data (this confirms the snapshot-mode fetch from GitHub's raw URL is working from inside this new container, not just that the process started). If it returns an empty `fixtures: []`, wait ~30s (the container's own `refresh_public_snapshot_from_remote` background poll needs one cycle) and retry.

- [ ] **Step 4: Write the CI workflow**

Create `PL_Predictor/.github/workflows/deploy-azure.yml` — identical structure to Task 4 Step 5's, with every `f1-predictor` replaced by `pl-predictor`:

```yaml
name: Deploy to Azure Container Apps

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read
  packages: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        run: |
          docker build -t ghcr.io/kevocado/pl-predictor:${{ github.sha }} -t ghcr.io/kevocado/pl-predictor:latest .
          docker push ghcr.io/kevocado/pl-predictor:${{ github.sha }}
          docker push ghcr.io/kevocado/pl-predictor:latest

      - name: Log in to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy new image to Container App
        run: |
          az containerapp update \
            --name pl-predictor \
            --resource-group predictor-hub-rg \
            --image ghcr.io/kevocado/pl-predictor:${{ github.sha }}
```

**Important:** this workflow triggers on every push to `main` — including the existing `refresh-public-snapshot.yml` Action's automated `data/public_snapshot.json` commits. That means every snapshot refresh (several times an hour during match windows) will now also rebuild and redeploy the whole Docker image, which defeats the entire reason that Action was built to avoid a full redeploy per data change (see `config.py`'s `PUBLIC_SNAPSHOT_REFRESH_URL` comment). Add a path filter so this workflow ignores snapshot-only commits:

```yaml
on:
  push:
    branches: [main]
    paths-ignore:
      - 'data/public_snapshot.json'
```
Add this `paths-ignore` block to the `on:` section above before committing.

- [ ] **Step 5: Commit and verify**

```bash
cd Prem_Predictor/PL_Predictor
git add .github/workflows/deploy-azure.yml
git commit -m "ci: deploy to Azure Container Apps on push to main"
git push
```
Watch it run (`gh run watch --repo Kevocado/PL_Predictor`), then confirm a new revision:
```bash
az containerapp revision list --name pl-predictor --resource-group predictor-hub-rg --output table
```

---

### Task 6: Deploy predictor-hub to Azure Static Web Apps and update its links

**Files:**
- Modify: `predictor-hub/index.html`

**Interfaces:**
- Consumes: F1's and PL's Container App FQDNs (Task 4 Step 4, Task 5 Step 3).
- Produces: a running Static Web App serving the updated hub page.

- [ ] **Step 1: Update the two existing card links and add the NFL "coming soon" card**

In `predictor-hub/index.html`, replace:

```html
    <a class="card" href="https://pl-predictor-l84f.onrender.com" target="_blank" rel="noopener">
      <span class="badge live">Live</span>
      <span class="card-icon">⚽</span>
      <h2>PL Predictor</h2>
      <p>Premier League match outcomes, scorelines, and player predictions built on a walk-forward-validated scoreline model.</p>
    </a>

    <a class="card" href="https://f1-predictor-ohio.onrender.com" target="_blank" rel="noopener">
      <span class="badge live">Live</span>
      <span class="card-icon">🏎️</span>
      <h2>F1 Predictor</h2>
      <p>Formula 1 race outcome, championship projection, and live in-race predictions, updated during live sessions.</p>
    </a>
  </div>
```

with (substituting the two real FQDNs from Task 4/5, and note the CSS already has a `.card.disabled`/`.badge.soon` pair ready for exactly this):

```html
    <a class="card" href="https://<PL_FQDN>" target="_blank" rel="noopener">
      <span class="badge live">Live</span>
      <span class="card-icon">⚽</span>
      <h2>PL Predictor</h2>
      <p>Premier League match outcomes, scorelines, and player predictions built on a walk-forward-validated scoreline model.</p>
    </a>

    <a class="card" href="https://<F1_FQDN>" target="_blank" rel="noopener">
      <span class="badge live">Live</span>
      <span class="card-icon">🏎️</span>
      <h2>F1 Predictor</h2>
      <p>Formula 1 race outcome, championship projection, and live in-race predictions, updated during live sessions.</p>
    </a>

    <div class="card disabled">
      <span class="badge soon">Coming soon</span>
      <span class="card-icon">🏈</span>
      <h2>NFL Predictor</h2>
      <p>Weekly game predictions and season projections — in development.</p>
    </div>
  </div>
```

- [ ] **Step 2: Verify locally before deploying**

Open `predictor-hub/index.html` directly in a browser (`open predictor-hub/index.html` on macOS) and confirm all three cards render, the PL/F1 links point at the new Azure URLs, and the NFL card shows dimmed with a "Coming soon" badge and isn't clickable.

- [ ] **Step 3: Commit**

```bash
cd predictor-hub
git add index.html
git commit -m "feat: point hub links at Azure, add NFL coming-soon card"
```

- [ ] **Step 4: Create the Static Web App, wired to auto-deploy from this repo**

Needs a GitHub personal access token with `repo` scope (the same kind used elsewhere in this plan, or reuse `$GITHUB_TOKEN` from Task 4 if it has `repo` scope too):

```bash
az staticwebapp create \
  --name predictor-hub \
  --resource-group predictor-hub-rg \
  --location eastus2 \
  --source https://github.com/Kevocado/predictor-hub \
  --branch main \
  --app-location "/" \
  --output-location "" \
  --sku Free \
  --token $GITHUB_TOKEN
```
This both creates the Static Web App **and** commits a GitHub Actions workflow file into `predictor-hub` for you (`.github/workflows/azure-static-web-apps-*.yml`) — no manual CI wiring needed here, unlike Tasks 4/5.

- [ ] **Step 5: Push and verify**

```bash
git push
gh run watch --repo Kevocado/predictor-hub
```
Expected: the auto-generated workflow completes green.

```bash
az staticwebapp show --name predictor-hub --resource-group predictor-hub-rg --query defaultHostname -o tsv
```
Open the printed hostname in a browser and confirm all three cards render correctly, and both live links load their respective apps.

---

### Task 7: Soak, then decommission Render

**Files:** none (Render dashboard/API only)

**Interfaces:** none — this is the final cutover step, gated on Task 6 being confirmed working.

- [ ] **Step 1: Soak period**

Leave both Render services running in parallel with Azure for a few days of real usage (a weekend, given this app's traffic pattern) — watch for anything Azure handles differently than Render (cold-start latency, odds-window timing, memory ceilling on real live traffic for F1). Do not proceed to Step 2 until you've seen at least one real weekend of traffic pass cleanly on Azure.

- [ ] **Step 2: Delete the two Render services**

Via the Render dashboard (Dashboard → select each service → Settings → scroll to bottom → Delete Service) for both the F1_Predictor and PL_Predictor Render services. There is no undo — confirm Azure has been serving correctly for real users before this step.

- [ ] **Step 3: Confirm nothing else pointed at the old Render URLs**

```bash
grep -rn "onrender.com" /Users/sigey/Documents/Projects/predictor-hub /Users/sigey/Documents/Projects/F1_Predictor /Users/sigey/Documents/Projects/Prem_Predictor/PL_Predictor --include="*.html" --include="*.ts" --include="*.tsx" --include="*.py" --include="*.md" 2>/dev/null
```
Expected: no matches (or only matches inside old design-spec/plan markdown files documenting history, which is fine to leave — they're not live config).

**Explicitly out of scope for this step:** do NOT delete or disable `PL_Predictor/.github/workflows/refresh-public-snapshot.yml` — Azure's `pl-predictor` deployment still depends on it exactly as Render's did (see Global Constraints above).
