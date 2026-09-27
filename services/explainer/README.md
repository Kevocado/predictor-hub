# Predictor explainer

Writes the "In plain English" panel for a match or F1 session. It reads the
facts bundle from the sport's own API, adds free ESPN headlines, asks an
OpenRouter free model for a short explanation, and shows it only if every
number in it came from those facts or headlines. Otherwise it uses a plain
template. Results are cached in SQLite, and a summary is made when a reader asks
for one — there is no background pre-generation.

## What it returns

```jsonc
{
  "sport": "nfl", "id": "401585",
  "verdict": "Baltimore is the pick, but the line is thinner than the number.",
  "band": "moderate",              // COMPUTED from pick.prob, never asked of the model
  "factors": [                    // 2-4, each naming a market the facts carry
    { "key": "moneyline", "direction": "up", "headline": "Model leans Baltimore",
      "text": "The rating gap has held all week." }
  ],
  "source": "llm", "model": "nemotron-3.5-lightning",
  "generated_at": "2026-10-05T00:20:00Z", "prompt_version": "v2",
  "pick_timing": "pre_kickoff"
}
```

Two properties worth knowing before changing anything here:

- **The model supplies no figure.** A factor is a *reference* to a market by
  `key`; the panel resolves it against the facts and draws the numbers itself.
  That is what makes the template path structurally as good as the model path —
  the layout is driven by the data the panel is handed and does not know which
  path produced it.
- **`band` is derived, not requested.** It is `contract.band_for(pick.prob,
  market_shape)`, with thresholds in the spec, and the model is not asked for
  one. A band is a *word*, and a word is the same defect as a number when
  nothing ties it to anything: a model can call a 52% pick "strong" and there is
  no fact to contradict it. `tests/test_service.py` proves it with a model that
  tries.

## Run

```sh
docker build -t predictor-explainer services/explainer
docker run -d --name predictor-explainer --network <the sites' network> \
  -v explainer-data:/data --env-file /etc/predictor/explainer.env predictor-explainer
```

Health and budget: `curl http://predictor-explainer:8090/status`, which returns
`{"used_today", "cap", "enabled", "model"}` and never any key material.

Locally, without Docker:

```sh
uv sync --extra dev
SPORT_API_NFL=http://127.0.0.1:8001 EXPLAINER_ENABLED=false \
EXPLAINER_DB_PATH=./explainer.sqlite \
  uv run uvicorn explainer.app:create_app --factory --host 127.0.0.1 --port 8090
```

`--factory` is required: there is no module-level `app` in `explainer/app.py`,
because building the app must not read settings or touch the database at import
time. `uvicorn explainer.app:app` fails with `Attribute "app" not found`.

`EXPLAINER_DB_PATH` is not optional. It defaults to `/data/explainer.sqlite`,
and startup creates that directory — a read-only filesystem outside a
container — so the lifespan raises `OSError` and the app never serves.

With `EXPLAINER_ENABLED=false` and no key, every explanation is the template
and the panel's footer reads "Summary written from the model's numbers". That
is the right way to bring this up: the panel is useful before it is clever, it
costs nothing, and it proves the whole path — site, proxy, service, the sport
API's `/facts`, and the panel — before a single request is spent.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | The only secret. Keep it in the env file on the VPS, never in a repo, a site build, a GitHub secret or a log. Unset means template only. |
| `EXPLAINER_MODEL` | `nvidia/nemotron-3.5-lightning:free` | First model tried. See the free-model section below before trusting it. |
| `EXPLAINER_FALLBACK_MODEL` | `poolside/laguna-s-2.1:free` | Tried once when the first fails or its answer is rejected. |
| `EXPLAINER_DAILY_CAP` | `900` | OpenRouter requests per UTC day, retries included (the account allows 1,000). Enforced by the ledger at spend time, so a refusal or a cache hit costs nothing. The old scheduler's 50-request headroom is gone with it: that headroom existed to stop pre-generation starving on-demand readers, and there is no pre-generation left to starve them. |
| `EXPLAINER_ENABLED` | `true` | `false` serves templates only, so the first uncached read is free while you check a rollout. |
| `EXPLAINER_DB_PATH` | `/data/explainer.sqlite` | Cache and daily ledger. Keep it on the volume. |
| `SPORT_API_PL`, `SPORT_API_F1`, `SPORT_API_NFL`, `SPORT_API_CFB`, `SPORT_API_NBA` | unset | Base URL of each sport API (the prefix before `/facts/...`). Unset sports return 404. **Serving is a separate list**: `config.SERVED_SPORTS` is `("pl", "nfl", "cfb")`, so `f1` and `nba` return 404 *even when their URL is configured* — the v2 panel is specified for three sports, and F1 and NBA are in `SPORTS` only so their config and their sites' proxies keep working while the frontend removal lands. `tests/test_unserved_sport.py` pins both halves. |

Run a single uvicorn worker: the per-match lock that stops two visitors
paying for the same explanation lives in the process.

## The free model IDs, and checking them

The defaults were `deepseek/deepseek-chat-v3-0324:free` and
`meta-llama/llama-3.3-70b-instruct:free`. **Both have been withdrawn from
OpenRouter's free tier.** The current pair, verified answering from the VPS:

| | |
|---|---|
| `EXPLAINER_MODEL` | `nvidia/nemotron-3.5-lightning:free` |
| `EXPLAINER_FALLBACK_MODEL` | `poolside/laguna-s-2.1:free` |

`qwen/qwen3.8-27b:free` and `google/gemma-4-26b-a4b-it:free` were tried at the
same time and were returning **429** — rate-limited, not withdrawn. A 429 is not
evidence that a model is gone, so it is not recorded as a withdrawal.

**A wrong model ID is the quietest failure in this service.** A non-200 raises
`LLMError`, the fallback is tried, and if that fails too the template is stored
and served. The reader gets a panel. The only symptom is that *every* panel is a
template, which looks like a design decision rather than an outage — see
`/status` and the `cap`/`used_today` counters, and watch for the template share
in the logs.

### Re-checking, from a machine with egress

OpenRouter is not reachable from every build environment, so this is a manual
step rather than a test. On the VPS:

```sh
# 1. What is actually on the free tier now.
curl -s https://openrouter.ai/api/v1/models | python3 -c \
  'import json,sys; [print(m["id"]) for m in json.load(sys.stdin)["data"] if m["id"].endswith(":free")]'

# 2. Does the one you intend to use actually ANSWER? Listing is not answering.
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"nvidia/nemotron-3.5-lightning:free","messages":[{"role":"user","content":"Reply with the single word: ok"}]}'
```

Step 2 is the one that matters and the one that is easy to skip: a model can be
listed and still 429 or 404 on completion. `tests/test_free_models.py` pins the
defaults against a whitelist of ids somebody has watched answer, so changing a
default to something unverified fails the suite.

## How a site reaches this service

**Every site calls `/api/explain/{sport}/{id}`.** That is the one path the spec,
the plan and all four site clients name, and it is what you should configure.
The service's own route is `/explain/{sport}/{id}` — the `/explain` prefix is
added by whichever proxy sits in front, never by the browser.

There are two shapes of proxy, because the sites are deployed two different ways.

**Sports** (NFL + CFB) is a static bundle behind its own Caddy, so the path is
translated at the edge. This mirrors the `/api/nfl` and `/api/cfb` blocks
already in that Caddyfile:

```
handle_path /api/explain/* {
    rewrite * /explain{uri}
    reverse_proxy {$EXPLAINER_UPSTREAM:predictor-explainer:8090}
}
```

`handle_path` drops `/api/explain`, and the `rewrite` puts back the `/explain`
this service serves. The equivalent `uri strip_prefix /api` also works; the
rewrite form is used because it matches the file it lives in.

**PL, NBA and F1** are served by their own FastAPI, which Caddy reverse-proxies
wholesale. Their `api/explain.py` router forwards to `EXPLAINER_URL` and is
where the path translation and the error handling are tested. Set:

| Var | Default | Meaning |
|---|---|---|
| `EXPLAINER_URL` | `http://predictor-explainer:8090` | This service, over the compose network. |
| `EXPLAINER_TIMEOUT_S` | `15` (PL), `10` (NBA, F1) | How long a site's proxy waits. Deliberately **below** the browser's own timeout (PL 20 s, NBA and F1 15 s): the proxy route is a sync `def`, so a request that outlasts the client occupies a worker thread for an answer nobody is waiting for. **A first uncached read is the slow case** — it pays for the model round trip, and may hit this and show the panel's Try again state. That is the cost of on-demand, and it is why the cap is worth watching; a second open of the same fixture is a cache hit and costs nothing. |

Each of those three also needs its Vite dev proxy to forward `/api/explain`, so
dev and production take the same path.

**If a summary fails, the page still works.** A missing explainer is a 502 with
a fixed message, never an upstream body — an upstream error could carry key
material. The site shows its own error state with Try again, and the game,
fixture or session underneath is unaffected. The panel is additive: with no
explainer deployed at all, the sites render exactly as they did before.

## Tests

```sh
uv sync --extra dev && uv run --extra dev python -m pytest -q
```

Run pytest **through the venv's python** (`python -m pytest`), not as bare
`uv run pytest`. The latter resolves whatever `pytest` is first on `PATH`,
which on a developer machine is the system one — a different interpreter with
different packages, so a suite can pass against dependencies the project never
pinned. That is not hypothetical: the same mistake made NFL's and CFB's suites
run against the wrong interpreter and fail collection with
`No module named 'cfbd'` while their own venvs imported it fine.

Tests never touch the network: OpenRouter and ESPN are mocked with `respx`,
and sport APIs with mocked routes.

## Rollout

Follow spec section 4's staged order. Each step is independently reversible,
and the kill switch is `EXPLAINER_ENABLED=false`, which serves templates
without touching a site or spending anything. The sites do not need a redeploy
at any step: the panel is already wired, and it renders nothing when the
explainer is unreachable.

**Before step 1**, on the VPS: add the explainer to `compose.yml` and the route
to the Caddyfile (both already edited in the working tree of the `vps-stack`
repo), then confirm `docker compose config` resolves and that
`curl http://predictor-explainer:8090/status` answers. Check the free model IDs answer, not just that they are listed
above while you are there.

1. **Service and NFL facts.** Set `EXPLAINER_ENABLED=false` and no key. Open an
   NFL game: the panel appears with the non-AI footer. Read three summaries
   against their facts and confirm every number is the model's. Then set
   `EXPLAINER_ENABLED=true` and add the key; the same games should now show the
   model and the AI footer.
2. **CFB, PL and NBA facts.** Add each `SPORT_API_*`. One game per sport. For
   PL and NBA, go through the site's own `/api/explain/...` proxy rather than
   the service directly, so the path translation is exercised.
3. **F1 facts and the race story.** Open a session. The panel is collapsed to
   the headline behind "Read the race story". Confirm a rebuilt session says
   "Rebuilt after the session".
4. **Watch `used_today` in `/status`.** On-demand spend is per reader now, so
   the number to watch is requests-per-unique-fixture rather than a steady climb
   every 3 h. Confirm a second visit to the same fixture is a cache hit and
   costs no budget — that property is what makes on-demand affordable, and it is
   the one to check first. `tests/test_unserved_sport.py` also asserts that a
   refused sport costs nothing at all.

Then **watch the ledger for a week**. Specifically: `used_today` against the
cap, how many explanations fall back to the template (a jump means the model or
its answers are failing, and the fallbacks are why the panel is still honest),
and whether any panel renders a number that is not in its facts.

`OPENROUTER_API_KEY` is set only in the explainer's environment. It is not in
any site bundle, any site's GitHub secret, any log line, or any test. The
per-site proxies turn upstream errors into a fixed 502 precisely so an upstream
message cannot carry it to a browser.
