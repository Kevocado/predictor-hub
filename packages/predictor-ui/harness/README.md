# Explainer panel — screenshot harness

Not a site. A review instrument: it renders every state the panel can be in,
from the same components and the same tokens the five Predictor sites use, so
what a screenshot shows is what ships.

```sh
npm install          # its own node_modules, on purpose
npm run typecheck    # tsc over main.tsx and vite.config.ts — see below
npm run build        # -> dist/
npm run preview      # http://localhost:4180
```

- `index.html` — every state, one after another
- `narrow.html` — the same page in a **390px** iframe. Headless Chrome on macOS
  will not open a window narrower than 500px, so the phone width is measured
  inside a frame rather than by resizing. Same origin, or the frame is
  cross-origin and unreadable.
- `insight.html` / `insight-narrow.html` — the fixture-insight mocks (cases 1–15)
  and the same page at 390px.
- `narrow.html`'s iframe trick is only needed for a **window**. A Playwright run
  that sets `viewport: { width: 390 }` measures the real thing and is what the
  `shots/pickslist-detail-*-390.png` captures used.

## Where the screenshots live, and how to re-shoot them

`shots/`, beside the page, and the name is the case id plus the width —
`pickslist-detail-qb-passing-tds-390.png` is `[data-shot="qb-passing-tds"]` at
390px. The `data-shot` attributes exist so a script can clip one state without
counting `div`s: `shots/pickslist-picks-component-desktop.png` is the precedent.

Two things a re-shoot must not lose. Read the rendered `textContent` of each row
back out of the page and print it — a screenshot proves a thing was drawn, only
the text says whether it was the right thing. And block every request the harness
does not serve itself, including `fonts.googleapis.com`: `src/fonts.css` imports
Barlow, and a capture taken with the CDN reachable and the fonts not yet settled
measures the fallback face and reports a layout a reader never gets.

## The mocks must use the strings a real adapter passes

Case 15 originally used a harness-shaped heading (`"Rush yds — projections, not
probabilities"`) with detail `"Rush yds"`, and every test was green. `Sports_Predictor`
`origin/main` `src/lib/picksPanel.ts:79` passes `category: "QB passing yards"` with
`detail: "Pass yds"` — an **abbreviation**, so the two share no token and the
de-duplication that worked in the mock did not work on the page. Three of that
panel's categories were affected, and a second defect rode along: the qualifier
was applied to every drawn detail, so a yardage estimate rendered as
`Pass yds · model call`.

A mock built on strings no adapter passes cannot catch a defect about real
strings. So the PicksList mocks copy the real `category`/`detail`/`kind` triples,
with the file and line each came from, and the same strings are pinned as tests
in `src/components/sportsPayloads.test.tsx`. When an adapter's wording changes,
change both, and the screenshots.

## Why it has its own dependencies

`resolve.dedupe` points React at one instance, but the deeper reason is that
adding a build tool to `predictor-ui`'s own `package.json` can disturb the
library's test run — which it did, on the first attempt, silently breaking six
test files. A review instrument must not be able to break the thing it reviews.

## Why it has its own tsconfig

The same reason, one step further on. `predictor-ui`'s `tsconfig.json` includes
`["src", "vitest.config.ts", "test-setup.ts"]`, so the harness sat outside every
type-checker in the repo — and it held a real type error for two commits before
anyone found it, in the file Kevin reads the panel from.

`npm run typecheck` now covers `main.tsx` and `vite.config.ts`, which drags the
library's 17 source files in behind them. The check is worth having because
**nothing else in this repo catches a type error here**: `vite build` transpiles
via esbuild, which strips types without reading them, so a harness with a type
error still builds to a working `dist/`. Both facts were measured — with the
defect reintroduced, `typecheck` exits 2 while `build` exits 0 and the library's
own `tsc --noEmit` exits 0. A screenshot is a worse place to find out.

**Nothing runs it automatically.** This repo has no CI on push or PR; its only
workflow is `workflow_dispatch` (the Azure deploy, run by hand). Until that
changes, `npm run typecheck` is run by a person, and the type of person is
whoever is about to re-shoot the screenshots.

The `@types` it needs are here rather than in the library: `main.tsx` imports
`react-dom/client`, and `predictor-ui` declares `@types/react` but never
`@types/react-dom`, because its own `src` imports only `react`. Versions match
what the library resolves — `@types/react@^19.2.17`, the same range it declares,
and `@types/react-dom@^19.3.0`, the React 19 counterpart of the 19.3.0 that
`@types/react` resolves to today.

## What it caught that tests could not

The record strip was gated on the v1 branch, so **every v2 panel silently
dropped its record** while 148 tests passed — because the component test rendered
`RecordStrip` directly and never through the panel. A screenshot is the only
instrument that reads the panel the way a reader does.
