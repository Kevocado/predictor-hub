# Plan: global navigation redesign + Paper Trading tab

Phase N0 — plan only. No code. Awaiting approval before N1.

Companion prompts: `NAV-REDESIGN-PROMPT.md`, `TRACK-RECORD-KIT-PROMPT.md`, `PAPER-TRADING-PROMPT.md`.
Design work run in `impeccable` Operate mode on the existing broadcast-scoreboard world (tokens, fonts, radius inherited; no new tokens/fonts/deps). Recorded decisions in "Design decisions from impeccable" below.

## 0. Decisions approved on hub#119 (override §8 where they conflict)

1. **Drop the aggregate "Data Hub" tab.** Promote its children to the SportTabs row. Canonical (unified) order/labels for the promoted data tabs: `Teams, Players, Standings, Power rankings, Projected table, Track record` (each sport shows the subset it has). Old deep links to `Data Hub`/`?tab=hub`/`#hub` keep working via redirect to the first promoted child (`Teams`). Game-list label stays sport-native: PL `Fixtures`, F1 `Races`, others `Games`.
2. **No "Home" tab.** The `Predictor` wordmark becomes a link to the hub home and carries `aria-current="page"` on the hub. GlobalNav entries are exactly: `Premier League | NFL | College football | NBA | F1 | Paper Trading`.
3. **Keep each site's existing URL scheme.** NBA keeps react-router paths (`/`, `/hub`→redirect, `/model`, `/calibration-report`); Sports keeps `?sport=&tab=`; PL and F1 gain hash tabs (`#fixtures`, `#races`, …). Browser back works via `hashchange`/`popstate`.
4. **NFL and "College football" entries** reach the shared Sports app via `?sport=nfl` / `?sport=cfb` (unchanged).
5. **Paper Trading**: hub white accent (`data-sport="hub"`), route `/paper.html`, on the hub domain.
6. **F1 token reskin is its own PR** (f1-* → pr-*) preceding F1 nav adoption; nav adoption then reuses AppFrame.
7. **GlobalNav is a single horizontally-scrolling row** (no wrap) with the fade rendered only when overflowing; active tab scrolled into view. Header height at 375px: GlobalNav row ≈ 44px; sport-page header (global + title + SportTabs) ≈ 130–150px (measured in N1).
8. **Sports_Predictor extras**: no `Top calls` or `Line checker` page exists (TopCalls is a component inside the game-detail modal). `Props` are not a standalone page either. None become tabs. Only the existing Hub sub-tabs are promoted.

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
- "Data Hub" aggregate is dropped (decision 1); its children are promoted to the SportTabs row in this canonical order: `Teams, Players, Standings, Power rankings, Projected table, Track record` (each sport shows the subset it has). Old `Data Hub` links redirect to the first promoted child (`Teams`).
- Promoted tab sets (N3):
  - PL: `Fixtures, Teams, Players, Power rankings, Projected table, Track record, FPL, Model/Calibration`
  - F1: `Races, Championship, Track record`
  - Sports (NFL/CFB): `Games, Teams, Players, Standings, Track record`
  - NBA: `Games, Teams, Players, Power rankings, Standings, Track record, Calibration, Model`
- F1 is the only site not on AppFrame and has no Data Hub; its 3 tabs stay, but theming is a separate PR (decision 6).
- `Top calls` / `Line checker` / `Props` are not standalone pages: `TopCalls` is a component inside NBA's game-detail modal; Sports_Predictor has no such page. None become tabs (decision 8). If any ships later it joins the row via the same `Tab[]`.

### NFL vs CFB (one app)
Both live in `Sports_Predictor` selected by `?sport=nfl|cfb`. The top bar needs two entries. Proposal:
- Keep `?sport=` as the sport selector (already deep-linkable and tested by `GamesPage.deepLink.test.tsx`).
- Top-bar entries: NFL → `https://sports.<host>/?sport=nfl`, CFB → `https://sports.<host>/?sport=cfb`.
- The app reads `sport` from the URL (existing `SportProvider`), so each entry lands on the right sport with its own accent (`data-sport`).
- Alternative (owner's `/sports#nfl` style hash) would avoid the query string but breaks the existing `?sport=` deep links and tests. Kept `?sport=` for lowest risk; flagged below.

## 2. Wireframes

### 2a. Home (375px)

```
┌────────────────────────────────────┐
│ [Predictor]  Premier League NFL College football NBA F1 Paper Trading  → │
│              (one scrolling row; fade only if overflow; active=none)      │
├────────────────────────────────────┤
│ Sports Predictor                   │  <- hero strip (wider banner)
│ Model picks for five sports…       │
│ [The rule strap]                   │
├────────────────────────────────────┤
│ ┌────┐ (board, 1 col)             │
│ │ PL │  teaser below               │
│ └────┘                             │
│ … 5 cards                          │
└────────────────────────────────────┘
```
GlobalNav row height ≈ 44px at 375px.

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
┌────────────────────────────────────┐
│ [Predictor]  Premier League NFL College football [NBA] F1 Paper Trading → │
│              (one scrolling row; NBA active; fade only if overflow)        │
├────────────────────────────────────┤
│ NBA Predictor                      │
│ Games Teams Players Power rankings Standings Track record Calibration Model → │
│ (SportTabs row, scrolls, fade only if overflow, active scrolled into view) │
├────────────────────────────────────┤
│ <active tab panel>                 │
└────────────────────────────────────┘
```
Sport-page header ≈ 130–150px at 375px.

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
  entries,          // sports + paper trading, in display order (no Home entry)
  activeId,         // id of the current entry, or null on hub home
  ariaLabel?,       // default "Sports"
}: Props): JSX.Element
```
- Approved entries (decision 2/4/5): `Premier League, NFL, College football, NBA, F1, Paper Trading` in that order. No Home entry; the `Predictor` wordmark is the home link and is `aria-current="page"` on the hub.
- Renders a `<nav aria-label>` of anchors (not buttons) — cross-subdomain navigation, real hrefs.
- Active entry: `aria-current="page"` + accent fill, matching AppFrame today.
- Single horizontally-scrolling row, fade only when overflowing, active scrolled into view (decision 7).
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
- Per-site scheme (approved decision 3):
  - NBA: keep react-router paths (`/`, `/model`, `/calibration-report`); old `/hub` keeps working via redirect to `/` with the first promoted tab (Teams) active.
  - Sports (NFL/CFB): `?sport=nfl|cfb&tab=<id>` (query, ignored by server; no VPS change). Default tab = Games when `tab` absent. Old `?sport=` links default to Games.
  - PL: hash tabs `#fixtures`, `#teams`, … (new; no old links to preserve).
  - F1: hash tabs `#races`, `#championship`, `#track-record` (new).
- Browser back: `popstate`/`hashchange` listener updates active tab; `history.pushState`/`replaceState` on change. PL/F1 need this added (currently no URL state).
- Redirects (decision 1): dropping the aggregate "Data Hub" tab means `?tab=hub`/`#hub`/`/hub` redirect to the first promoted child (Teams) so old links never 404.
## 5. Hub home shares the bar
Choice: **vanilla twin, not a React render.**
- Reason: the hub has no build step and is served by Caddy `file_server`; adding React would add a build + bundle and break the "static, fast at kickoff" property.
- The twin is ~40 lines of HTML/CSS mirroring GlobalNav's markup and `pr-*` tokens; tokens are already inlined and drift-tested.
- No "Home" entry (decision 2): the `Predictor` wordmark is the home link and carries `aria-current="page"` on the hub. GlobalNav entries on the hub are exactly `Premier League | NFL | College football | NBA | F1 | Paper Trading`.
- Drift guard: extend `tests/hub.test.mjs` to assert the bar's nav has the six approved entry labels in order, plus the token assertions already there. Add a snapshot assertion for the active-entry markup (`aria-current="page"` + accent fill) matching GlobalNav's output.

## 6. Phases and rollout

- **N0** (this PR): plan doc only. Docs PR to predictor-hub. ← you are here
- **N1**: predictor-ui — `GlobalNav`, `SportTabs`, tests (ARIA roles, keyboard, 375px no clipped tab/no horizontal page scroll, active/aria-current, overflow fade only when overflowing). Hub PR. Depends on track-record-kit (HubTabs) already on main (merged).
- **N2**: hub home — banner + bar + existing teasers, same aesthetic. Hub PR. Update hub.test.mjs.
- **N3**: vendor into each site, one PR per site, `node scripts/sync-ui.mjs --from <hub-sha> <site>/<src>` (src for Sports_Predictor, frontend/src for NBA/PL/F1; never `--vendor-anyway`). Each site lists its full promoted tab set in the SportTabs row (decision 1 canonical order; sport-specific tabs appended). Page content unchanged; capture before/after page text.
  - F1 is two PRs (decision 6): (a) f1-* → pr-* token reskin, content unchanged; (b) vendor AppFrame + GlobalNav + SportTabs with tabs `Races, Championship, Track record`.
- **N4**: Paper Trading page (hub) — reads `data/paper/report.json` only, built from Track Record kit (RecordHeadline, calibration, recent rows, HowCounted), mandatory early-sample banner, per-segment table with current-model n / all-time n, every figure labelled "paper", stakes in paper units only. Route `/paper.html`. Starts with whatever segments exist; "cannot be judged yet" is the normal state. Build after agent A produces real settled rows unless owner says otherwise.

### VPS/Caddy changes
- No new subdomain or proxy for the nav itself (hash/query based tabs never reach the server).
- Paper Trading page: new static file `/paper.html` on the hub domain; Caddy `file_server` serves it. No Caddyfile change; ensure `bin/deploy` ships it.
- NBA keeps paths; old `/hub` handled by a client-side redirect to the first promoted tab. No Caddy change.
- NFL/CFB `?sport=` + `?tab=` ignored by the server. No change.
- Real domain later: hostnames in entries change; no structural change.

## 7. Design decisions from impeccable (Operate mode)
- Operate mode: scanability and native expectations over expression; brand in precise details.
- Inherited world (broadcast scoreboard) unchanged: near-black stage, one raised panel, hard 1px rules, 6px radius, Barlow/Barlow Condensed, one hot accent per sport on the top border. No glow/gradient/emoji.
- Top bar is a single shared component across all surfaces (home + every sport + paper trading) so it reads as one product; active entry highlighted with accent fill + stage ink (existing AppFrame convention).
- Labels use full names per owner ("Premier League", "College football") rather than abbreviations, for the new tab bar; sport codes (PL, NFL, …) stay on the cards.
- Overflow handled inside the bar (horizontal scroll + conditional fade + scroll-into-view), never widening the page — required at 375px.
- Hub home keeps the torn-off-strip picks board below the wider banner; banner is "bar + hero strip" only.
- Paper Trading uses hub theming (no new accent token) and the Track Record kit components; every figure labelled "paper".

## 8. Remaining open questions (post-approval)
1. Game-list tab label: keep sport-native (`Fixtures`/`Races`/`Games`) or unify to `Games` everywhere? Recommendation: keep sport-native.
2. Whether to keep a redirect shim for the dropped `Data Hub` aggregate at `/hub` → first promoted child, or 404? Recommendation: redirect (decision 1).
3. F1 reskin scope: reskin all f1-* tokens to pr-* in the reskin PR, or only the surfaces AppFrame touches? Recommendation: all (one coherent world).

## 9. Acceptance (N0)
- Docs only; no source/test changes.
- Plan reviewed and approved before N1 starts.
- No merge or deploy.
