# Plan: global navigation redesign + Paper Trading tab

Phase N0 — plan only. No code. Awaiting approval before N1.

Companion prompts: `NAV-REDESIGN-PROMPT.md`, `TRACK-RECORD-KIT-PROMPT.md`, `PAPER-TRADING-PROMPT.md`.
Design work run in `impeccable` Operate mode on the existing broadcast-scoreboard world (tokens, fonts, radius inherited; no new tokens/fonts/deps). Recorded decisions in "Design decisions from impeccable" below.

## 1. Inventory of current tabs/pages

### React sites (AppFrame-based unless noted)

| Sport | Site | Current top-level tabs | Route mechanism | Hidden pages (reachable today) |
|---|---|---|---|---|
| PL | PL_Predictor | Fixtures, Data Hub, FPL, Calibration/Model (public: "Model") | in-memory state (no URL) | Data Hub sub-tabs: Team Hub, Player Hub, Power Rankings, Projected Table, Track Record |
| F1 | F1_Predictor | Races, Championship, Track Record | in-memory state (no URL); bespoke layout, **not** on AppFrame | none |
| NFL + CFB | Sports_Predictor (one app, `?sport=`) | Games, Data Hub | query param `?sport=nfl\|cfb` + in-memory tab | Data Hub sub-tabs: Teams, Players, Standings, Track record |
| NBA | NBA_Predictor | Games, Data Hub, Calibration, Model | react-router paths (`/`, `/hub`, `/calibration-report`, `/model`) | Data Hub sub-tabs: Teams, Players, Power rankings, Standings, Track record |
| Hub | predictor-hub | Home (self), PL, F1, NFL, CFB, NBA | static anchors | teasers per sport |

### Notes
- "Data Hub" is an aggregate tab whose children (Teams/Players/Standings/Track record/Power rankings/Projected table) are the real pages. N3 promotes those children to the SportTabs row and drops the aggregate (or keeps it as an overview — see Open questions).
- F1 is the only site not on AppFrame and has no Data Hub; its 3 tabs stay as-is in N3 (adopt AppFrame + GlobalNav, content unchanged).
- No "picks/props" or "line checker" page exists anywhere today; the prompt's list was illustrative. If either ships later it joins the row via the same `Tab[]`.

### NFL vs CFB (one app)
Both live in `Sports_Predictor` selected by `?sport=nfl|cfb`. The top bar needs two entries. Proposal:
- Keep `?sport=` as the sport selector (already deep-linkable and tested by `GamesPage.deepLink.test.tsx`).
- Top-bar entries: NFL → `https://sports.<host>/?sport=nfl`, CFB → `https://sports.<host>/?sport=cfb`.
- The app reads `sport` from the URL (existing `SportProvider`), so each entry lands on the right sport with its own accent (`data-sport`).
- Alternative (owner's `/sports#nfl` style hash) would avoid the query string but breaks the existing `?sport=` deep links and tests. Kept `?sport=` for lowest risk; flagged below.

## 2. Wireframes

### 2a. Home (375px)

```
┌──────────────────────────────┐
│ Predictor                    │  <- wordmark (links home)
│ Premier League NFL CFB NBA … │  <- GlobalNav, scrolls; active=none
│ F1 Paper Trading             │     (fade only if overflow)
├──────────────────────────────┤
│ Sports Predictor             │  <- hero strip (wider banner)
│ Model picks for five sports… │
│ [The rule strap]             │
├──────────────────────────────┤
│ ┌────┐┌────┐ (board, 1 col) │
│ │ PL ││ …  │                 │
│ │teaser│                      │
│ └────┘                      │
│ … 5 cards                   │
└──────────────────────────────┘
```

### 2b. Home (desktop, ≥1152px)

```
┌──────────────────────────────────────────────────────────────┐
│ Predictor   Premier League  NFL  College football  NBA  F1  Paper Trading │
├──────────────────────────────────────────────────────────────┤
│ Sports Predictor                                             │
│ Model picks for five sports, each with reasoning and record   │
│ [The rule strap]                                             │
├──────────────────────────────────────────────────────────────┤
│ [PL][NFL][CFB][NBA][F1]  (5 cards in one row, teasers below) │
└──────────────────────────────────────────────────────────────┘
```

### 2c. Sport page, 8+ tabs (NBA, 375px)

```
┌──────────────────────────────┐
│ Predictor                    │
│ Premier League NFL CFB NBA F1│  <- GlobalNav (NBA active)
│ Paper Trading                │
├──────────────────────────────┤
│ NBA Predictor                │
│ Games  Teams  Players  Power…│  <- SportTabs (HubTabs), scrolls
│ …rankings  Standings  Track  │     fade only if overflow;
│ record  Calibration  Model    │     active scrolled into view
├──────────────────────────────┤
│ <active tab panel>           │
└──────────────────────────────┘
```

### 2d. Sport page (desktop)

```
┌──────────────────────────────────────────────────────────────┐
│ Predictor   Premier League  NFL  College football  NBA  F1  Paper Trading │
├──────────────────────────────────────────────────────────────┤
│ NBA Predictor                                                │
│ Games  Teams  Players  Power rankings  Standings  Track record  Calibration  Model │
├──────────────────────────────────────────────────────────────┤
│ <active tab panel>                                           │
└──────────────────────────────────────────────────────────────┘
```

### 2e. Paper Trading page (375px)

```
┌──────────────────────────────┐
│ Predictor                    │
│ … Paper Trading (active)     │
├──────────────────────────────┤
│ Paper Trading                │
│ <early-sample banner>        │
│ per-segment table            │
│ RecordHeadline / calibration │
│ / recent rows / HowCounted   │
└──────────────────────────────┘
```

### Overflow behavior (SportTabs and GlobalNav)
- Container: `overflow-x: auto`, `scrollbar-width: none` (or thin), no page-level horizontal scroll.
- Fade: a right-edge gradient overlay rendered **only** when `scrollWidth > clientWidth + 1` (measured via ResizeObserver + scroll listener). Not always (current HubTabs always shows it — N1 fixes).
- Active tab scrolled into view on change: `activeRef.current?.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" })`, guarded for reduced motion.
- Keyboard (inherited from HubTabs): ArrowLeft/Right, Home, End, roving tabindex.
- 375px acceptance: no clipped tab label, no horizontal page scroll.

## 3. Component API

In `packages/predictor-ui`.

### `GlobalNav`
```ts
export type NavEntry = { id: string; label: string; href: string; sport?: Sport };
export function GlobalNav({
  entries,          // sports + paper trading, in display order
  activeId,         // id of the current entry, or null on home
  ariaLabel?,       // default "Sports"
}: Props): JSX.Element
```
- Renders a `<nav aria-label>` of anchors (not buttons) — cross-subdomain navigation, real hrefs.
- Active entry: `aria-current="page"` + accent fill, matching AppFrame today.
- Reuses only `pr-*` tokens; no new deps/fonts.
- Sport accent comes from the host page's `data-sport` (hub = white).

### `SportTabs`
```ts
export function SportTabs({
  tabs,             // HubTab[]
  active,           // string
  onChange,         // (id) => void
  panels?,          // optional, passed through to HubTabs
  label?,           // default "Pages"
  className?,
}: Props): JSX.Element
```
- Thin wrapper over `HubTabs` (trackRecord/HubTabs) that adds the overflow-fade-only-when-overflowing + scroll-into-view behavior. All ARIA/keyboard inherited from HubTabs.
- Sites pass their full tab set here.

### `AppFrame` (updated)
```ts
type Props = {
  sport: Sport;            // add "paper"? see Open questions
  sportName: string;
  sites: SiteLink[];       // becomes the GlobalNav entries' source (or replaced)
  paperTradingHref: string;
  tabs: Tab[];
  activeTab: string;
  onTab: (id: string) => void;
  children: ReactNode;
};
```
- Composes `<GlobalNav>` (top bar) + title + `<SportTabs>` (second row) + children.
- `sites` stays for back-compat during migration; N3 switches to entries.

### Export additions in `src/index.ts`
`GlobalNav`, `SportTabs`, and their types. No other new exports.

## 4. Deep links
- Every `SportTabs` tab has a stable id; the active id is read from the URL on mount and written on change.
- Proposed scheme (per site, lowest-risk):
  - NBA: keep react-router paths (`/games`? no — keep `/`, `/hub`, …). Add tab ids to paths; existing `/hub` stays.
  - Sports (NFL/CFB): `?sport=nfl&tab=games` (query, ignored by server; no VPS change). Migrate from in-memory to query-driven with a default.
  - PL: hash `#fixtures`, `#hub`, … (was in-memory; hash needs no server change).
  - F1: hash `#races`, `#championship`, `#track-record`.
- Browser back: `popstate`/`hashchange` listener updates active tab; `history.pushState` on change. PL/F1 need this added (currently no URL state).
- Open question: unify on one scheme (hash everywhere) vs keep per-site schemes. Recommendation: hash everywhere for zero VPS impact, with redirects from NBA's old paths. Flagged.

## 5. Hub home shares the bar
Choice: **vanilla twin, not a React render.**
- Reason: the hub has no build step and is served by Caddy `file_server`; adding React would add a build + bundle and break the "static, fast at kickoff" property.
- The twin is ~40 lines of HTML/CSS mirroring GlobalNav's markup and `pr-*` tokens; tokens are already inlined and drift-tested.
- Drift guard: extend `tests/hub.test.mjs` to assert the bar's nav has the same entry labels/order as a shared constant, plus the token assertions already there. Additionally, a small `tests/hub-nav.test.mjs` (or a section in hub.test.mjs) asserts the active-entry markup pattern (`aria-current="page"` + accent fill) matches what AppFrame/GlobalNav produces (snapshot of expected HTML fragment). This is the "test that keeps them from drifting."

## 6. Phases and rollout

- **N0** (this PR): plan doc only. Docs PR to predictor-hub. ← you are here
- **N1**: predictor-ui — `GlobalNav`, `SportTabs`, tests (ARIA roles, keyboard, 375px no clipped tab/no horizontal page scroll, active/aria-current, overflow fade only when overflowing). Hub PR. Depends on track-record-kit (HubTabs) already on main (merged).
- **N2**: hub home — banner + bar + existing teasers, same aesthetic. Hub PR. Update hub.test.mjs.
- **N3**: vendor into each site, one PR per site, `node scripts/sync-ui.mjs --from <hub-sha> <site>/<src>` (src for Sports_Predictor, frontend/src for NBA/PL/F1; never `--vendor-anyway`). Each site lists its full tab set in the SportTabs row. Page content unchanged; capture before/after page text.
- **N4**: Paper Trading page (hub) — reads `data/paper/report.json` only, built from Track Record kit (RecordHeadline, calibration, recent rows, HowCounted), mandatory early-sample banner, per-segment table with current-model n / all-time n, every figure labelled "paper", stakes in paper units only. Starts with whatever segments exist; "cannot be judged yet" is the normal state. Build after agent A produces real settled rows unless owner says otherwise.

### VPS/Caddy changes
- No new subdomain or proxy for the nav itself (hash/query based tabs never reach the server).
- Paper Trading page: new static HTML file on the hub domain (e.g. `/paper-trading.html` or `/paper.html`); Caddy `file_server` serves it. No Caddyfile change; ensure `bin/deploy` ships it (it syncs the hub checkout to `/srv/hub`).
- If NBA migrates from path routes to hashes (open question), existing `/hub`, `/model`, `/calibration-report` URLs should keep working via a client-side redirect shim (no Caddy change). If instead we keep paths, no change.
- NFL/CFB `?sport=` already works; `?tab=` is ignored by the server. No change.
- Real domain later: hostnames in `SITES`/entries change; no structural change.

## 7. Design decisions from impeccable (Operate mode)
- Operate mode: scanability and native expectations over expression; brand in precise details.
- Inherited world (broadcast scoreboard) unchanged: near-black stage, one raised panel, hard 1px rules, 6px radius, Barlow/Barlow Condensed, one hot accent per sport on the top border. No glow/gradient/emoji.
- Top bar is a single shared component across all surfaces (home + every sport + paper trading) so it reads as one product; active entry highlighted with accent fill + stage ink (existing AppFrame convention).
- Labels use full names per owner ("Premier League", "College football") rather than abbreviations, for the new tab bar; sport codes (PL, NFL, …) stay on the cards.
- Overflow handled inside the bar (horizontal scroll + conditional fade + scroll-into-view), never widening the page — required at 375px.
- Hub home keeps the torn-off-strip picks board below the wider banner; banner is "bar + hero strip" only.
- Paper Trading uses hub theming (no new accent token) and the Track Record kit components; every figure labelled "paper".

## 8. Open questions (for approval)
1. SportTabs row: drop the aggregate "Data Hub" tab in favour of its children, or keep "Data Hub" as an overview tab plus children? Recommendation: drop aggregate (cleaner, matches "all tabs reachable in 2 clicks").
2. Hub "Home" entry: keep a separate Home tab in GlobalNav (existing) or make the wordmark the only home affordance? Recommendation: keep Home tab (existing tests expect `["Home","PL",…]` order) — but the owner's list omits it. Flagged.
3. Deep-link scheme: hash everywhere (recommended, zero VPS impact) vs per-site existing schemes. Flagged.
4. NFL/CFB top-bar selector: `?sport=` (recommended) vs `#nfl`/`#cfb`. Flagged.
5. Paper Trading accent: hub white (recommended, no new token) vs dedicated token. Flagged.
6. Paper Trading route path: `/paper.html` vs `/paper-trading.html`. Flagged (cosmetic).
7. F1 adoption of AppFrame in N3 changes its visual world from bespoke f1-* tokens to pr-* tokens — is that in scope for N3 "page content must not change"? Theming is not content, but it is a visible change. Flagged; recommend theming migration is part of N3 since GlobalNav requires pr-* tokens.

## 9. Acceptance (N0)
- Docs only; no source/test changes.
- Plan reviewed and approved before N1 starts.
- No merge or deploy.
