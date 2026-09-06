# Predictor Hub — Azure Hosting Migration Design Spec

## Overview

Migrate F1_Predictor, PL_Predictor, and (once built) NFL_Predictor off Render
onto Azure, using the free Azure for Students subscription, and unify them
under `predictor-hub`. Two problems this solves beyond "change host":

1. **PL_Predictor's snapshot workaround.** Render's free tier OOMs
   (512MB ceiling) on PL_Predictor's live feature pipeline, so it currently
   serves a precomputed `public_snapshot.json` refreshed hourly by a GitHub
   Action (`refresh-public-snapshot.yml`). Azure Container Apps gives each
   app several GB of RAM, removing the reason the snapshot exists.
2. **Fragmented hosting.** Each app is deployed and updated independently
   today; this migration keeps that independence (separate failure domains)
   but puts them under one Resource Group and one hub entry point.

An earlier version of this plan targeted Hugging Face Spaces, but Docker/
Gradio Spaces on HF's free tier now require a PRO subscription (confirmed
live: `hf repos create --space-sdk docker` returns `402 Payment Required`).
Azure was chosen instead because the user has an Azure for Students
subscription and Azure Container Apps' free grant covers this workload
without needing that credit for steady-state operation.

## Goals

- F1 and PL running live (no snapshot-serving) on Azure, reachable at all
  times (scale-to-zero, not always-off).
- One hub site linking to both, with a reserved/disabled slot for NFL.
- Effectively $0/month steady-state cost — the Azure for Students $100
  credit is a buffer, not a dependency.
- Push-to-deploy, matching today's Render auto-deploy workflow.
- Render fully decommissioned once Azure is verified.

## Non-goals

- No merged single-domain app (each backend keeps its own URL; the hub
  links out, it doesn't reverse-proxy or iframe).
- No NFL deployment yet — NFL_Predictor isn't built. This spec's pattern
  should apply to it unchanged once it reaches the same "one Dockerfile,
  FastAPI + built frontend" shape as its siblings.
- No always-on / zero-cold-start hosting. "Live" means real-time
  computation instead of a snapshot, not a guarantee against the 2-10s
  wake-up delay after idle. Confirmed acceptable given weekend-heavy,
  hobby-scale traffic.
- No custom domain for now (Static Web Apps supports one later if wanted).

## Current State (for reference)

| App | Host today | Mode | Auth |
|---|---|---|---|
| F1_Predictor | Render (free) | `PUBLIC_MODE=true`, live compute | none |
| PL_Predictor | Render (free) | `PUBLIC_MODE=true`, serves `data/public_snapshot.json` (refreshed by `.github/workflows/refresh-public-snapshot.yml`, cron `7 11-22 * * *`) | `GuestAuthMiddleware` (password gate) |
| NFL_Predictor | not deployed | n/a (design spec + in-progress worktree only) | n/a |
| predictor-hub | Render (static-ish) | single `index.html`, two cards linking to the Render URLs | none |

Both F1 and PL already build to a single Docker image (FastAPI backend +
built React frontend served from one origin, one process) — see each
repo's `Dockerfile`. This shape carries over to Azure unchanged.

## Target Architecture

### Topology

One Azure Resource Group (e.g. `predictor-hub-rg`), containing:

- One **Container Apps Environment**, shared by all backend apps (the
  free grant is per-subscription, so sharing an environment is purely for
  simpler management, not a cost optimization).
- **`f1-predictor`** — Container App, Consumption plan.
- **`pl-predictor`** — Container App, Consumption plan.
- **`nfl-predictor`** — reserved name, not created until NFL_Predictor ships.
- **`predictor-hub`** — Azure Static Web App (Free tier), the landing page.

Each Container App keeps its own URL
(`https://<app>.<region>.azurecontainerapps.io`); the hub links to them,
it does not merge them into one domain.

### Per-app changes

**F1_Predictor** — no code changes. Dockerfile already reads `PORT` from
env; Container Apps' `--target-port` is set to match whatever the
Dockerfile exposes (no forced port, unlike HF Spaces' 7860 requirement).

**PL_Predictor** — two changes, both already de-risked by F1's existing
live-compute pattern:
- Remove `GuestAuthMiddleware` from the public deployment path (drop the
  password gate — confirmed acceptable, matches F1's public/no-login shape).
- Stop serving from `public_snapshot.json`; run the same live feature
  pipeline the private/full app uses. Once nothing reads the snapshot,
  retire `public_snapshot.py`, `data/public_snapshot.json`, and
  `.github/workflows/refresh-public-snapshot.yml` — dead weight once live
  compute works, not left behind "just in case."

**NFL_Predictor** — no work now; this spec's pattern applies once it
reaches parity with F1/PL's single-Dockerfile shape.

**predictor-hub** — update the two card links from `*.onrender.com` to the
new Azure Container Apps URLs; add a third card for NFL, disabled/labeled
"coming soon" (no link) until it's deployed.

### Deployment pipeline

Mirrors today's "push to `main`, host picks it up" flow, Azure-native:

1. **Backends (F1, PL):** a GitHub Actions workflow in each repo builds
   the existing `Dockerfile` and pushes to GitHub Container Registry
   (`ghcr.io/kevocado/<app>:latest` — free for public images, no Azure
   Container Registry needed). Azure Container Apps' built-in GitHub
   Actions integration (`az containerapp github-action add`, run once
   during setup) watches for new images and rolls out a new revision
   automatically — no hand-rolled `az containerapp update` step needed.
2. **Hub:** `az staticwebapp create --source <predictor-hub repo>` wires
   up Static Web Apps' own native GitHub Actions deploy-on-push, same as
   the backends.

Each app's Container App config: `ingress external`, `target-port`
matching its Dockerfile, `min-replicas 0`, `max-replicas 1` (a single
instance is enough for hobby-scale weekend traffic; raise later only if
real usage demands it).

### Cost model

Azure Container Apps' always-free monthly grant (per subscription, not
per app): 180,000 vCPU-seconds, 360,000 GiB-seconds, 2,000,000 requests.
With `min-replicas 0` across all 3 backend apps and weekend-concentrated
hobby traffic, this should comfortably stay inside the free grant —
steady-state cost is expected to be **$0/month**. Azure Static Web Apps'
Free tier (100GB bandwidth/month) is free indefinitely, unrelated to any
credit. The $100 Azure for Students credit is a safety margin for
unexpected spikes, not something the design relies on to keep running —
if traffic ever grew past the free grant, cost only starts accruing past
that grant, and it's proportional to actual usage (no bill risk from a
purely idle month).

### Cutover plan

1. Stand up `f1-predictor` and `pl-predictor` Container Apps; verify each
   serves correctly and PL computes live without OOM.
2. Update `predictor-hub`'s links to the new Azure URLs; add the NFL
   "coming soon" card.
3. Let it run for a short soak period, watching for cold-start issues or
   unexpected errors.
4. Decommission: delete the two Render services, delete PL's
   `refresh-public-snapshot.yml` Action and `public_snapshot.py` machinery.

## Testing / Verification

- Each Container App: hit its root and a representative API route after a
  cold start (confirm the 2-10s wake-up, then correct response) and again
  warm (confirm normal latency).
- PL_Predictor specifically: confirm live-computed responses match what
  the removed snapshot used to serve (spot-check a few fixtures), and
  confirm memory stays well under the Container App's configured limit
  under a realistic request burst (no OOM).
- Hub: confirm both links resolve to the live Azure apps, and the NFL card
  renders as disabled/coming-soon.

## Open Risks

- Cold-start latency for ML-model-loading apps (F1/PL load trained model
  files at startup) may exceed the generic "2-10s for small containers"
  estimate — needs a real measurement once deployed, not assumed.
- GHCR image pulls from Container Apps for public images are documented
  as straightforward (`az containerapp registry set --server ghcr.io`),
  but this hasn't been executed yet in this project — first real deploy
  is where this gets confirmed, not assumed from documentation alone.
