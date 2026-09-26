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
