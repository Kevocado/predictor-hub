# Predictor explainer

Writes the "In plain English" panel for a match or F1 session. It reads the
facts bundle from the sport's own API, adds free ESPN headlines, asks an
OpenRouter free model for a short explanation, and shows it only if every
number in it came from those facts or headlines. Otherwise it uses a plain
template. Results are cached in SQLite and pre-generated every 3 hours for
what starts in the next 72 hours.

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
  uv run uvicorn explainer.app:create_app --factory --host 127.0.0.1 --port 8090
```

`--factory` is required: there is no module-level `app` in `explainer/app.py`,
because building the app must not read settings or touch the database at import
time. `uvicorn explainer.app:app` fails with `Attribute "app" not found`.

With `EXPLAINER_ENABLED=false` and no key, every explanation is the template
and the panel's footer reads "Summary written from the model's numbers". That
is the right way to bring this up: the panel is useful before it is clever, it
costs nothing, and it proves the whole path — site, proxy, service, the sport
API's `/facts`, and the panel — before a single request is spent.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | The only secret. Keep it in the env file on the VPS, never in a repo, a site build, a GitHub secret or a log. Unset means template only. |
| `EXPLAINER_MODEL` | `deepseek/deepseek-chat-v3-0324:free` | First model tried. |
| `EXPLAINER_FALLBACK_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | Tried once when the first fails or its answer is rejected. |
| `EXPLAINER_DAILY_CAP` | `900` | OpenRouter requests per UTC day, retries included (the account allows 1,000). Pre-generation stops 50 short, leaving those for on-demand use. |
| `EXPLAINER_ENABLED` | `true` | `false` serves templates only and stops pre-generation. |
| `EXPLAINER_DB_PATH` | `/data/explainer.sqlite` | Cache and daily ledger. Keep it on the volume. |
| `SPORT_API_PL`, `SPORT_API_F1`, `SPORT_API_NFL`, `SPORT_API_CFB`, `SPORT_API_NBA` | unset | Base URL of each sport API (the prefix before `/facts/...`). Unset sports return 404. |

Run a single uvicorn worker: the per-match lock that stops two visitors
paying for the same explanation lives in the process.

## Before going live: check the free model IDs

Free model IDs on OpenRouter change. On the VPS:

```sh
curl -s https://openrouter.ai/api/v1/models | python3 -c \
  'import json,sys; [print(m["id"]) for m in json.load(sys.stdin)["data"] if m["id"].endswith(":free")]'
```

If either default is missing, set `EXPLAINER_MODEL` / `EXPLAINER_FALLBACK_MODEL`
to a listed `:free` model and restart. A wrong ID is safe (every request falls
back to the template), but you lose the written explanations until it's fixed.

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
| `EXPLAINER_TIMEOUT_S` | `30` | Longer than this service's own 25 s call plus its fallback retry, so a slow model is not cut off mid-answer. |

Each of those three also needs its Vite dev proxy to forward `/api/explain`, so
dev and production take the same path.

**If a summary fails, the page still works.** A missing explainer is a 502 with
a fixed message, never an upstream body — an upstream error could carry key
material. The site shows its own error state with Try again, and the game,
fixture or session underneath is unaffected. The panel is additive: with no
explainer deployed at all, the sites render exactly as they did before.

## Tests

```sh
uv sync --extra dev && uv run pytest -q
```

Tests never touch the network: OpenRouter and ESPN are mocked with `respx`,
and sport APIs with mocked routes.

## Rollout

Follow spec section 4's staged order. Each step is independently reversible,
and the kill switch is `EXPLAINER_ENABLED=false`, which serves templates and
stops pre-generation without touching a site. The sites do not need a redeploy
at any step: the panel is already wired, and it renders nothing when the
explainer is unreachable.

**Before step 1**, on the VPS: add the explainer to `compose.yml` and the route
to the Caddyfile (both already edited in the working tree of the `vps-stack`
repo), then confirm `docker compose config` resolves and that
`curl http://predictor-explainer:8090/status` answers. Check the free model IDs
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
4. **Turn on pre-generation.** It runs every 3 h and stops 50 requests short of
   the cap. Watch `used_today` in `/status` climb, and confirm the cache is
   being hit on a second visit (a repeat request costs no budget).

Then **watch the ledger for a week**. Specifically: `used_today` against the
cap, how many explanations fall back to the template (a jump means the model or
its answers are failing, and the fallbacks are why the panel is still honest),
and whether any panel renders a number that is not in its facts.

`OPENROUTER_API_KEY` is set only in the explainer's environment. It is not in
any site bundle, any site's GitHub secret, any log line, or any test. The
per-site proxies turn upstream errors into a fixed 502 precisely so an upstream
message cannot carry it to a browser.
