# Phase 2a · `predictor-ui` package — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) task by task. Steps use checkbox (`- [ ]`) syntax.
>
> **Design sub-skill:** `/impeccable extract`. Read `reference/craft-floor.md` before any component markup. Run `impeccable detect` on the component files at the end.

**Goal:** a vendorable package that gives every Predictor site the same tokens, number formatting, state components and card grammar. It changes no site yet; that happens in 2b onwards.

**Architecture:**
- The package lives at `predictor-hub/packages/predictor-ui/`, with its own Vitest setup.
- Contents:
  - `tokens.css`: CSS variables inside a Tailwind v4 `@theme` block, plus `[data-sport=…]` accent overrides.
  - `fmt.ts`: pure functions.
  - React components styled with Tailwind utilities that read those tokens.
- `scripts/sync-ui.mjs` vendors `src/` into a site's `src/predictor-ui/` and writes a checksum manifest.

**Tech stack:** TypeScript, React 19 (peer), Vitest 2, Testing Library, jsdom.

**Spec:** [../specs/2026-09-25-phase2-family-design-system.md](../specs/2026-09-25-phase2-family-design-system.md), sections 2, 4, 5 and 6.

## Global constraints

- **Components are look-agnostic of sport.** They read `--color-pr-accent`, never a sport colour directly.
- **Every visible number goes through `fmt`.**
- **No text under 12 px, and no meaning carried by colour alone.** Every status carries a word.
- **Contrast is enforced by test:**
  - text and dim text on stage and panel: 4.5:1 or better;
  - each accent on stage: 3:1 or better;
  - accent ink on its accent: 4.5:1 or better.
- **Craft-floor refusals:** no gradient text, no glass, no coloured `border-left` above 1 px, no hard offset shadows, no emoji as icons.
- `fmt` uses a true minus sign (U+2212) for negatives.

## Review focus

1. `pct` at the edges (0, 1, 0.005, 0.995) must never print "0%" or "100%" for a live probability.
2. `margin` and `spread` with negative zero (`-0`) or `NaN` input print "Toss-up" or "—", never "NaN".
3. `kickoff` in a zone that has no short name still shows an offset.
4. The `ProbabilityBar` three-way order is always Home, Draw, Away. The two-way order follows the header prop (away first for US sports).
5. `sync-ui` run twice gives the same checksums, and an edited vendored file fails the site's check.

---

### Task 1: package scaffold and `fmt`

**Files:** create:
- `packages/predictor-ui/package.json`, `tsconfig.json`, `vitest.config.ts`
- `packages/predictor-ui/src/fmt.ts`, `packages/predictor-ui/src/fmt.test.ts`

**Interfaces (produces):** `pct`, `pctFine`, `stat`, `signed`, `streak`, `margin`, `spread`, `record`, `kickoff`, `modelDate`, with exactly the input and output pairs in spec §5.

- [ ] Write `fmt.test.ts` asserting every row of spec §5, plus Review focus items 1–3.
- [ ] Run it and watch it fail (module missing).
- [ ] Implement `fmt.ts`.
- [ ] Run it and confirm it passes. Commit: `feat(predictor-ui): fmt — the one owner of on-screen numbers`.

### Task 2: tokens and contrast gate

**Files:** create:
- `src/tokens.css`
- `src/contrast.ts`: WCAG relative luminance and ratio
- `src/tokens.test.ts`

**Interfaces (produces):** CSS custom properties.
- Neutrals: `--color-pr-stage`, `-panel`, `-panel-2`, `-rule`, `-text`, `-text-dim`, `-text-faint`.
- Accent: `--color-pr-accent`, `-accent-ink`.
- Status: `--color-pr-win`, `-loss`, `-lean`.
- Fonts: `--font-pr-display`, `--font-pr-body`.
- Radius: `--radius-pr`.
- Sport overrides: `[data-sport="pl"|"f1"|"nfl"|"cfb"|"nba"|"hub"]` each set `--color-pr-accent` and `--color-pr-accent-ink`.

- [ ] Write `tokens.test.ts`. It parses `tokens.css`, collects the hex values for each scope, and asserts the Global Constraints contrast rules for every sport scope and every text/surface pair.
- [ ] Watch it fail.
- [ ] Write `tokens.css` and `contrast.ts`, adjusting hex values until the gate passes. Record the final values in the commit body.
- [ ] Commit: `feat(predictor-ui): tokens with an enforced contrast gate`.

### Task 3: state and atom components

**Files:** create `src/components/{StatusBadge,TeamChip,StatTile,States}.tsx`, each with a `.test.tsx`.

**Interfaces (produces):**
- `StatusBadge({ status: "next" | "live" | "called" | "missed" | "nopick" | "rebuilt" })`: fixed words "Next up", "Live", "Called it ✓", "Missed ✗", "No pick yet", "Rebuilt after kickoff".
- `TeamChip({ code, color, name? })`: an `aria-label` of the full name when given. The ink colour is chosen by contrast against `color`.
- `StatTile({ label, value, sub? })`.
- `Skeleton({ label })`: `role="status"`, and the label is read out.
- `EmptyState({ message, action? })`.
- `ErrorState({ message, onRetry })`: `role="alert"`, with a "Try again" button.

- [ ] Tests for each, including TeamChip ink selection on a light colour (#F5B301 gives dark ink) and a dark one (#0B2265 gives light ink).
- [ ] Watch them fail, implement, watch them pass, commit.

### Task 4: `ProbabilityBar` and `MatchCard`

**Files:** create `src/components/{ProbabilityBar,MatchCard}.tsx` plus tests.

**Interfaces (produces):**
- `ProbabilityBar({ segments: { label: string; prob: number; color?: string }[] })`.
  - Segments render in the given order.
  - Every segment has a visible text label with `fmt.pct`.
  - `role="img"` with an `aria-label` such as "Home 36%, Draw 26%, Away 38%".
- `MatchCard({ left, right, centre, pick?, status, bar?, meta?, onOpen })`.
  - `left` and `right` are `{ code, name, color?, badge? }`, where `badge` is a ReactNode for crests.
  - `centre` is a kickoff string or a score.
  - `pick` is `{ label, prob }` and renders "Pick: {label} · {pct}".
  - `status` is a `StatusBadge` status.
  - The root is a real `<button>` so Enter and Space both work. Its accessible name summarises the pick.

- [ ] Tests:
  - three-way order (Review focus 4);
  - two-way away-first;
  - "Pick: Aston Villa win · 38%";
  - Space activates;
  - a card with no pick shows "No pick yet";
  - only one status badge is rendered.
- [ ] Watch them fail, implement, watch them pass, commit.

### Task 5: frame, switcher, tabs, round navigator

**Files:** create `src/components/{AppFrame,RoundNavigator}.tsx` plus tests.

**Interfaces (produces):**
- `AppFrame({ sport, tabs, activeTab, onTab, sites, children })`.
  - Renders the wordmark "PREDICTOR" and the sport name ("NBA Predictor").
  - The `SportSwitcher` is a `<nav aria-label="Sports">` of links to `sites`, with the current one marked `aria-current="page"`.
  - `PageTabs` is a `role="tablist"` of buttons.
  - Sets `data-sport` on the root so the accent applies.
- `RoundNavigator({ label, canPrev, canNext, onPrev, onNext, onJumpToCurrent?, record? })`.
  - `record` is `{ hits, settled, rebuilt }` and renders with the Phase 1 copy: "{hits}/{settled} picks made before kickoff correct", or "No pre-kickoff picks this {unit}".

- [ ] Tests for the current-site marking, `data-sport`, tab switching, the prev/next disabled states and the record copy, including the rebuilt-only case.
- [ ] Watch them fail, implement, watch them pass, commit.

### Task 6: sync script and drift check

**Files:** create:
- `scripts/sync-ui.mjs`
- `packages/predictor-ui/src/index.ts` (barrel)
- `tests/sync-ui.test.mjs`

**Behaviour:**
- `node scripts/sync-ui.mjs <site-src-dir>` copies `packages/predictor-ui/src/**` (excluding tests) into `<site-src-dir>/predictor-ui/`.
- It prepends a do-not-edit header naming the hub commit, and writes `SYNC.json` with a sha256 per file.
- `node scripts/sync-ui.mjs --check <site-src-dir>` exits 1 if any file's hash differs from `SYNC.json`.

- [ ] A `node:test` suite in a temp dir: sync twice gives identical `SYNC.json`; editing a copied file makes `--check` exit 1.
- [ ] Watch it fail, implement, watch it pass, commit.

### Task 7: verification

- [ ] `npx vitest run` and `npx tsc --noEmit` in the package; `node --test tests/` at the hub root.
- [ ] Run `impeccable detect --json packages/predictor-ui/src` and fix any finding.
- [ ] Fresh whole-branch review (superpowers:requesting-code-review). Fix Critical and Important findings in one pass.
- [ ] Push `claude/sports-predictors-frontend-plan-qpab3v`. The open hub PR picks this up.

## Self-review

- **Spec coverage:** §5 → Task 1; §2 type, stage and status plus §4 tokens → Task 2; §2 status and states → Task 3; §6 `MatchCard` and `ProbabilityBar` → Task 4; §2 frame and games page plus §6 frame components → Task 5; §4 distribution → Task 6. The spec's `TimingTower`, `NextUpHero`, `StatTable` and `DetailSheet` are deferred to the plans that first use them (2b and 2e), to follow YAGNI.
- **Types:** `StatusBadge`'s status union is shared by `MatchCard`. The `record` shape `{ hits, settled, rebuilt }` matches Phase 1's `prekickoffTally`.
