/**
 * Fixture-insight mocks for the 2026-09-30 spec — NOT a shipped surface.
 *
 * Review instrument only: the instant block is composed from the REAL
 * predictor-ui components (StatusBadge, KeyNumberTile, ProbabilityBar,
 * RecordStrip, BoxScore, SummaryButton) with fixture-shaped data, so
 * layout, tokens and type carry over to implementation. The callout /
 * player-pick / filter pieces are static proposal markup (marked
 * PROPOSAL): they show intent for the spec's screenshots, not a
 * component to import. Case 16 (`signals`) is SHIPPED, like cases 13-15.
 *
 * ONE FIXTURE feeds every NFL mock below (spec §2 correction round):
 * GB at ATL, week 6. Change a number here and every mock follows, so two
 * mocks can never disagree about the same game the way the first draft's
 * callouts ("model −6.1") and tiles did.
 */
import { useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  StatusBadge,
  KeyNumberTile,
  ProbabilityBar,
  RecordStrip,
  BoxScore,
  SummaryButton,
  InstantBlock,
  PicksList,
  SignalRows,
  SPEC_MIN_N,
  MAX_HEADLINE_WORDS,
  signalIsDrawn,
  UndrawableSignalVisualError,
  type MarketTile,
  type Segment,
  type BoxScoreGroup,
  type PickRow,
  type OutPlayer,
  type PicksListProps,
  type Signal,
} from "../src/index";
import {
  FIX,
  PLAYERS,
  LISTS,
  CATEGORY_KIND,
  SIGNALS,
  BELOW_FLOOR_SIGNAL,
  LONG_HEADLINE_SIGNAL,
  BUCKET,
  trustRate,
  ranked,
  outPlayers,
  valueOf,
  assertFixtureConsistency,
  type Category,
  ABSENCE_SIGNAL,
  PL_ABSENCE_SIGNAL,
} from "./fixture";

/** The game and every player figure live in ./fixture — nothing restates them. */
const pct = (p: number) => `${Math.round(p * 100)}%`;

const NFL_TILES: MarketTile[] = [
  { market: "moneyline", label: "moneyline", value: pct(FIX.homeWinProb), sub: `win · ${FIX.home}` },
  { market: "spread", label: "spread", value: `${FIX.home} ${FIX.spreadLine}`, sub: `model ${FIX.home} ${FIX.modelMargin}` },
  { market: "total", label: "total", value: String(FIX.predictedTotal), sub: `total pts · line ${FIX.totalLine}` },
];
const NFL_SEGMENTS: Segment[] = [
  { label: FIX.home, prob: FIX.homeWinProb, market: "moneyline" },
  { label: FIX.away, prob: FIX.awayWinProb, market: "moneyline" },
];

const PL_TILES: MarketTile[] = [
  { market: "result", label: "result", value: "57%", sub: "win · Arsenal" },
  { market: "total_goals", label: "total goals", value: "2.7" },
  { market: "btts", label: "both score", value: "61%" },
];
const PL_SEGMENTS: Segment[] = [
  { label: "Arsenal", prob: 0.57, market: "result" },
  { label: "Draw", prob: 0.24, market: "result" },
  { label: "Chelsea", prob: 0.19, market: "result" },
];
const PL_LEGEND: Segment[] = [
  { label: "Arsenal", prob: 0.55, market: "result" },
  { label: "Draw", prob: 0.25, market: "result" },
  { label: "Chelsea", prob: 0.2, market: "result" },
];

const NBA_TILES: MarketTile[] = [
  { market: "moneyline", label: "moneyline", value: "64%", sub: "win · BOS" },
  { market: "spread", label: "spread", value: "BOS -4.5", sub: "model BOS -4.2" },
  { market: "total", label: "total", value: "221.4", sub: "total pts · line 222.5" },
];
const NBA_SEGMENTS: Segment[] = [
  { label: "BOS", prob: 0.64, market: "moneyline" },
  { label: "MIA", prob: 0.36, market: "moneyline" },
];

function Verdict({ children }: { children: React.ReactNode }) {
  return (
    <p className="min-w-0 max-w-[70ch] text-lg font-medium leading-snug text-pr-text">{children}</p>
  );
}

function InstantHead({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-dim">
      {children}
    </h3>
  );
}

function Case({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="flex flex-col gap-3 border-t border-pr-rule p-5 first:border-t-0">
      <h2 className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-faint">{title}</h2>
      {note && <p className="-mt-1 max-w-[70ch] text-xs text-pr-text-faint">{note}</p>}
      <div className="max-w-[46rem]">{children}</div>
    </section>
  );
}

/** The real `SignalRows` with every disclosure opened, so the shot shows the
 *  evidence line rather than the control that hides it.
 *
 *  Done by clicking the real buttons the component rendered — the same event a
 *  keyboard Enter raises on a button — rather than by reaching into the DOM to
 *  unhide a node, which would photograph a state nothing produces. The
 *  `aria-expanded` transition and the Tab-then-Enter path are asserted in
 *  `src/components/SignalRows.test.tsx`; this is the pixels. */
function OpenEvidence({ signals }: { signals: Signal[] }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    host.current
      ?.querySelectorAll<HTMLButtonElement>('[data-testid="signal-evidence-toggle"]')
      .forEach((b) => b.click());
  }, [signals]);
  return <div ref={host}><SignalRows signals={signals} /></div>;
}

/** What the refusal looks like, on the page: the error's own words, which is all
 *  a reader would ever get, since nothing renders.
 *
 *  Called through the exported `signalIsDrawn` rather than through a render,
 *  because React's own render path is not a thing a harness can catch
 *  synchronously — a `try` around `createRoot().render()` reads as though it
 *  were testing the refusal and tests nothing at all. The exported predicate is
 *  the guard `SignalRows` filters on, so exercising it exercises the gate; the
 *  render-time throw is asserted in `SignalRows.test.tsx`. */
function RefusedVisual() {
  const absence: Signal = { ...BELOW_FLOOR_SIGNAL, kind: "absence", visual: "absence_strip" };
  let message: string;
  try {
    signalIsDrawn(absence);
    message = "NOT REFUSED — this is the defect the case exists to catch.";
  } catch (err) {
    message = err instanceof UndrawableSignalVisualError ? err.message : `${String(err)}`;
  }
  return (
    <p data-testid="signals-refusal" className="max-w-[70ch] rounded-pr border border-pr-loss p-3 text-xs leading-snug text-pr-loss">
      {message}
    </p>
  );
}

/** PROPOSAL markup: static, not a component. Shows intent only. */
function Proposal({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-pr border border-dashed border-pr-rule p-3">
      <p className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-faint">
        Proposal · {label} · not a component
      </p>
      {children}
    </div>
  );
}

function Callout({ delta, deltaTone, text, evidence }: { delta: string; deltaTone: string; text: string; evidence: string }) {
  return (
    <div className="flex items-start gap-3 rounded-pr border border-pr-rule bg-pr-panel px-3 py-2">
      <span className={`shrink-0 rounded-pr px-2 py-1 font-pr-display text-xs font-semibold tabular-nums ${deltaTone}`}>
        {delta}
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-medium leading-snug text-pr-text">{text}</p>
        <p className="text-xs text-pr-text-faint">{evidence}</p>
      </div>
    </div>
  );
}

/** A probability row: share bar from the real ProbabilityBar + graded record. */
function ProbRow({ name, detail, p, record }: { name: string; detail: string; p: number; record: string }) {
  return (
    <div className="flex flex-col gap-1 border-t border-pr-rule py-2 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-pr-text">{name} <span className="font-normal text-pr-text-dim">· {detail}</span></p>
        <p className="shrink-0 text-sm font-semibold tabular-nums text-pr-text">{pct(p)}</p>
      </div>
      <ProbabilityBar segments={[{ label: detail, prob: p, market: "pick" }, { label: "rest", prob: 1 - p, market: "pick" }]} minSegmentPx={2} />
      <p className="text-xs text-pr-text-faint">{record}</p>
    </div>
  );
}

/** A projection row: key number from the real KeyNumberTile + margin. */
function ProjRow({ name, detail, value, sub, record }: { name: string; detail: string; value: string; sub: string; record: string }) {
  return (
    <div className="flex items-center gap-3 border-t border-pr-rule py-2 first:border-t-0 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-pr-text">{name} <span className="font-normal text-pr-text-dim">· {detail}</span></p>
        <p className="text-xs text-pr-text-faint">{record}</p>
      </div>
      <div className="w-36 shrink-0"><KeyNumberTile tile={{ market: "pick", label: detail, value, sub }} /></div>
    </div>
  );
}

const BOX_COLUMNS = [
  { key: "yds", label: "Yds" },
  { key: "td", label: "TD%" },
];
// Built from PLAYERS, so the box score cannot disagree with the picks about
// the same player: Yds reads the rush-yardage projection, TD% the anytime-TD
// probability. Jacobs is out: he gets no projection row, which is why the out
// line below the lists matters.
const BOX_GROUPS_BOTH: BoxScoreGroup[] = [
  {
    position: `${FIX.home} · RB`,
    rows: [
      {
        key: "wilson",
        name: PLAYERS.wilson.name,
        position: "RB",
        team: FIX.home,
        order: 1,
        isStarter: true,
        values: [
          valueOf(PLAYERS.wilson, "Rush yds"),
          Math.round(valueOf(PLAYERS.wilson, "Anytime TD") * 100),
        ],
      },
    ],
    subtotals: [{ label: `${FIX.home} total`, values: [valueOf(PLAYERS.wilson, "Rush yds"), null] }],
  },
  {
    position: `${FIX.away} · RB`,
    rows: [
      {
        key: "robinson",
        name: PLAYERS.robinson.name,
        position: "RB",
        team: FIX.away,
        order: 1,
        isStarter: true,
        values: [
          valueOf(PLAYERS.robinson, "Rush yds"),
          Math.round(valueOf(PLAYERS.robinson, "Anytime TD") * 100),
        ],
      },
    ],
    subtotals: [{ label: `${FIX.away} total`, values: [valueOf(PLAYERS.robinson, "Rush yds"), null] }],
  },
];

/**
 * The review's four findings, as code that runs when the mock loads: one
 * fixture means one number, no out player is ranked, one category per list,
 * and no row of the wrong KIND (a yardage figure read as a probability).
 * Throws with every problem named, rather than rendering a wrong mock.
 */
assertFixtureConsistency(
  LISTS.flatMap(({ category }) =>
    ranked(category).map((p) => ({ category, playerKey: p.key, value: valueOf(p, category) })),
  ),
  BOX_GROUPS_BOTH.flatMap((g) => g.rows.map((r) => ({ key: r.key, values: r.values }))),
);

/**
 * The fixture, in the SHIPPED component's own props — the shape Tasks 2-5 will
 * build from their adapters. Nothing here is a literal number: every `value`
 * and every `margin` comes from `valueOf(p, category)` / `p.mae`, so the mocks
 * above and this component cannot disagree about a player.
 */
const PICKS_PROPS: PicksListProps = (() => {
  const categories = LISTS.map(({ category }) => {
    const kind = CATEGORY_KIND[category as Category];
    const rows: PickRow[] = ranked(category as Category).map((p) => {
      const v = valueOf(p, category as Category);
      return {
        key: `${p.key}:${category}`,
        name: p.name,
        team: p.team,
        detail: category,
        value: v,
        kind,
        // Provenance is the CALLER's words, verbatim. Which words are honest is
        // the adapter's problem (the plan's corrections 1 and 2 land there), so
        // this reads the fixture's own record rather than composing a sentence.
        provenance:
          kind === "probability"
            ? `model ${pct(v)} · bucket hits ${pct(p.bucket!.hits)} · n=${p.bucket!.n}`
            : p.bucket
              ? `MAE ${p.mae![category]} · n=${p.bucket.n}`
              : "projection, not a probability · no graded record yet",
        ...(kind === "projection" ? { margin: p.mae?.[category as Category] } : {}),
      };
    });
    // One category per list, and the words say which kind each list holds.
    return {
      category: `${category === "Points" || category === "Rebounds" ? "NBA " : ""}${category}${
        kind === "projection" ? " — projections, not probabilities" : ""
      }`,
      rows,
    };
  });
  const out: OutPlayer[] = outPlayers().map((p) => ({
    name: p.name,
    team: p.team,
    source: "official injury report · via nfl_data_py",
    dated: "Sep 30, 2026",
  }));
  return { categories, out };
})();

const never = () => new Promise<unknown>(() => {});
const noop = () => {};

/**
 * Case 15's categories: Sports_Predictor's REAL heading/detail pairs, copied
 * from `origin/main` `src/lib/picksPanel.ts` rather than invented.
 *
 * That is a change from the first version of this case, and it is the change
 * review forced. The original case used a harness-shaped heading
 * (`"Rush yds — projections, not probabilities"`) with detail `"Rush yds"`,
 * where the two tokenise to the same words — so the de-duplication worked in
 * the harness and failed on the page, because the real rows abbreviate
 * (`"Pass yds"` under `"QB passing yards"`). A screenshot harness built on
 * strings that no real adapter passes cannot catch a defect about real strings.
 * The same rows are pinned in src/components/sportsPayloads.test.tsx; these are
 * the pixels.
 *
 * The QB lines follow the plan's rule (nearest half point to the projection,
 * floor 0.5). `detailLabel: "model line"` is the caller's own noun, per the
 * plan's "never a sportsbook line" — and note that the yardage rows pass no
 * `detailLabel` and get no qualifier at all, which is the point: a projection
 * is not a call.
 */
const QB_PASSING_TD_CATEGORY: PicksListProps["categories"][number] = {
  category: "QB passing TDs", // picksPanel.ts:121
  rows: [
    { key: "pass:rodgers", name: "A. Rodgers", team: "PIT", detail: "Over 2.5", detailLabel: "model line", value: 0.64, kind: "probability" },
    { key: "pass:allen", name: "J. Allen", team: "BUF", detail: "Over 1.5", detailLabel: "model line", value: 0.58, kind: "probability" },
    { key: "pass:burrow", name: "J. Burrow", team: "CIN", detail: "Under 2.5", detailLabel: "model line", value: 0.53, kind: "probability" },
  ],
};

/** picksPanel.ts:79 — heading `"QB passing yards"`, detail `"Pass yds"`, projection.
 *  An ABBREVIATED restatement: `{pass, yds}` shares no token with
 *  `{qb, passing, yards}`, so the token half of the rule alone would draw it. */
const QB_PASSING_YARDS_CATEGORY: PicksListProps["categories"][number] = {
  category: "QB passing yards",
  rows: [
    { key: "pass:rodgers", name: "A. Rodgers", team: "PIT", detail: "Pass yds", value: 284, kind: "projection", margin: 41 },
    { key: "pass:allen", name: "J. Allen", team: "BUF", detail: "Pass yds", value: 271, kind: "projection", margin: 41 },
    { key: "pass:burrow", name: "J. Burrow", team: "CIN", detail: "Pass yds", value: 262, kind: "projection", margin: 41 },
  ],
};

/** picksPanel.ts:116 / :256 — `detail: tdCategory` is the heading's own text, and
 *  this row is `kind: "probability"`, so the KIND gate cannot suppress it and
 *  the token half is the only thing standing between this card and its own
 *  heading printed three times. */
const NFL_TD_CATEGORY: PicksListProps["categories"][number] = {
  category: "Rush or receiving TD",
  rows: [
    { key: "td:rodgers", name: "A. Rodgers", team: "PIT", detail: "Rush or receiving TD", value: 0.41, kind: "probability" },
    { key: "td:alllen", name: "J. Allen", team: "BUF", detail: "Rush or receiving TD", value: 0.38, kind: "probability" },
    { key: "td:chase", name: "J. Chase", team: "CIN", detail: "Rush or receiving TD", value: 0.31, kind: "probability" },
  ],
};

/** The bundle shapes the two live block cases below feed `InstantBlock`, in the
 *  shape each site's adapter already builds. Nothing here is restated as prose:
 *  the block reads the same object the flow did. */
const NFL_BUNDLE = {
  home_team: FIX.home,
  home_team_full: "Green Bay",
  away_team: FIX.away,
  home_win_prob: FIX.homeWinProb,
  away_win_prob: FIX.awayWinProb,
  pick: { label: FIX.home, prob: FIX.homeWinProb },
} as const;

const F1_BUNDLE = {
  driver: "Max Verstappen",
  pick: "Max Verstappen",
  pick_timing: "unknown",
  session_start: null,
} as const;

function App() {
  return (
    <main data-sport="nfl" className="min-h-screen bg-pr-stage font-pr-body text-pr-text">
      <Case id="nfl-rebuilt" title="1 · NFL rebuilt — the instant block"
        note="Before: badge, tiles, bar and verdict appeared only after pressing Get the AI summary. After: they render from the site bundle with no request. The flow sentences (Win probabilities…, The model picks…) and the Match Markets repeat are gone.">
        <div className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <StatusBadge status="rebuilt" moment="kickoff" />
            <span>This pick was made after the game started. Counted in the track record like any other pick.</span>
          </p>
          <Verdict>{FIX.pick} is the pick.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NFL_SEGMENTS} minSegmentPx={2} pick={{ label: FIX.home }} />
          <RecordStrip label="Picks made before kickoff" hits={FIX.recordHits} settled={FIX.recordSettled} />
        </div>
      </Case>

      <Case id="prebutton" title="2 · pre-button state — complete facts, honest button"
        note="The block must look finished before any AI is fetched. The button promises what it adds (static site copy, no figures): model vs line, trends, who's out.">
        <div className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <span className="inline-flex items-center whitespace-nowrap rounded-pr border border-pr-rule px-1.5 py-0.5 font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-dim">
              Made before kickoff
            </span>
          </p>
          <Verdict>{FIX.pick} is the pick.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NFL_SEGMENTS} minSegmentPx={2} pick={{ label: FIX.home }} />
          <RecordStrip label="Picks made before kickoff" hits={FIX.recordHits} settled={FIX.recordSettled} />
          <div className="flex flex-col gap-1">
            <SummaryButton request={never} onSummary={noop} onUnavailable={noop} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">AI read: model vs line, trends, who&apos;s out.</p>
          </div>
        </div>
      </Case>

      <Case id="pl-pre" title="3 · PL pre-kickoff — three-way bar plus market row"
        note="The market's own row draws only because implied covers every outcome. Same instant block, three-way market. (Different game from the NFL mocks by nature: Arsenal v Chelsea.)">
        <div data-sport="pl" className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <span className="inline-flex items-center whitespace-nowrap rounded-pr border border-pr-rule px-1.5 py-0.5 font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-dim">
              Made before kickoff
            </span>
          </p>
          <Verdict>Arsenal is the pick.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {PL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={PL_SEGMENTS} legend={PL_LEGEND} minSegmentPx={2} pick={{ label: "Arsenal" }} />
          <RecordStrip label="Picks made before kickoff" hits={38} settled={71} />
        </div>
      </Case>

      <Case id="f1-unknown" title="4 · F1 — unverified timing, reduced block"
        note="F1 draws no market-line tiles and no split-bar market row (unchanged). The session badge names what the schedule did not supply.">
        <div data-sport="f1" className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <StatusBadge status="unverified" moment="the session" />
            <span>The schedule did not provide the start time, so this pick cannot be shown as made before the start.</span>
          </p>
          <Verdict>Max Verstappen is the pick.</Verdict>
          <RecordStrip label="Picks made before the session" hits={9} settled={14} />
        </div>
      </Case>

      <Case id="nba-now" title="5 · NBA — verdict and record join the instant tiles"
        note="Tiles stay where they are. New: the verdict line and the record strip. PregamePick prose is replaced by the timing badge once NBA promotes its flow pick_timing to the panel — not repeated beside it.">
        <div data-sport="nba" className="flex flex-col gap-3">
          <Verdict>Boston is the pick.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NBA_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NBA_SEGMENTS} minSegmentPx={2} pick={{ label: "BOS" }} />
          <RecordStrip label="Picks made before tip-off" hits={22} settled={40} />
        </div>
      </Case>

      <Case id="no-pick" title="6 · no pick — numbers without a claim"
        note="Tiles and an unaccented bar still inform; nothing is for or against anything, and the nopick badge says why.">
        <div className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <StatusBadge status="nopick" moment="kickoff" />
          </p>
          <Verdict>There is no pick for this one yet.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NFL_SEGMENTS} minSegmentPx={2} />
        </div>
      </Case>

      <Case id="news" title="7 · player news present vs absent"
        note="Present: an attributed, dated flag that moves the affected pick — never a recommendation of a player who is out. Absent: the block says nothing at all.">
        <div className="flex flex-col gap-3">
          <InstantHead>With news</InstantHead>
          <div className="flex items-start gap-3 rounded-pr border border-pr-rule bg-pr-panel px-3 py-2">
            <span className="shrink-0 rounded-pr px-2 py-1 font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-loss">
              Out
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <p className="text-sm font-medium leading-snug text-pr-text">{PLAYERS.jacobs.name} is out — the RB ranking moves to {PLAYERS.wilson.name}.</p>
              <p className="text-xs text-pr-text-faint">Official injury report · {PLAYERS.jacobs.team} · week 6 · via nfl_data_py</p>
            </div>
          </div>
          <InstantHead>Without news</InstantHead>
          <p className="max-w-[70ch] text-xs text-pr-text-faint">(no news element renders — the block says nothing)</p>
        </div>
      </Case>

      <Case id="callouts" title="8 · AI insight — callouts, not paragraphs (proposal)"
        note="Two scannable rows, both derived from the one fixture above: the disagreement is model −6.1 against line −4.5 (gap 1.6, the tile's own figures — the interpretation is new, the numbers are not). Anything without a fact behind it is rejected by the validator.">
        <Proposal label="insight callouts">
          <Callout delta={`▲ ${FIX.edge} pts`} deltaTone="text-pr-win"
            text={`The model wants more than the market on ${FIX.pick}.`}
            evidence={`Model ${FIX.home} ${FIX.modelMargin} vs line ${FIX.home} ${FIX.spreadLine} · last 10 GB covers: 7`} />
          <Callout delta="7–3" deltaTone="text-pr-text-dim"
            text={`${FIX.pick} covers after rest: 7 of the last 10.`}
            evidence="Trend over the stored pre-kickoff record · n=10" />
        </Proposal>
      </Case>

      <Case id="picks" title="9 · best player picks — top 3 per category, visual (proposal)"
        note="Probability rows get a share bar (real ProbabilityBar); projection rows get a key number with its margin (real KeyNumberTile). One category per list. Out players leave the ranking entirely and appear once, below the lists, attributed — never with a bar, a tile or a bold number. Every figure is read from harness/fixture.ts; assertFixtureConsistency throws if a mock ever restates one.">
        <Proposal label="player picks">
          {LISTS.map(({ category }) => (
            <div key={category} className={category === LISTS[0].category ? "" : "pt-2"}>
              <InstantHead>
                {category === "Points" || category === "Rebounds" ? "NBA " : ""}
                {category} — top {ranked(category).length}
                {CATEGORY_KIND[category as Category] === "projection" ? " (projections, not probabilities)" : ""}
              </InstantHead>
              {ranked(category).map((p) => {
                const v = valueOf(p, category);
                return CATEGORY_KIND[category] === "probability" ? (
                  <ProbRow key={p.key} name={`${p.name} (${p.team})`} detail={category}
                    p={v}
                    record={`model ${pct(v)} · bucket hits ${pct(p.bucket!.hits)} · n=${p.bucket!.n}`} />
                ) : (
                  <ProjRow key={p.key} name={`${p.name} (${p.team})`} detail={category}
                    value={String(v)} sub={`± ${p.mae![category]} MAE`}
                    record={p.bucket
                      ? `MAE ${p.mae![category]} · n=${p.bucket.n}`
                      : "projection, not a probability · no graded record yet"} />
                );
              })}
            </div>
          ))}
          {/* §D: an out player is shown ONCE, here, and nowhere in a ranking. */}
          {outPlayers().map((p) => (
            <p key={p.key} data-testid="out-player-line" className="pt-2 text-xs text-pr-text-faint">
              Out: {p.name} · official injury report · {p.team} · week 6 — not ranked above
            </p>
          ))}
        </Proposal>
      </Case>

      <Case id="picks-component" title="13 · SHIPPED PicksList — the real component, real atoms"
        note="Not a proposal: this is src/components/PicksList.tsx, rendering the fixture's own ranked players. Probability rows draw the real ProbabilityBar with minSegmentPx=2; projection rows draw the real KeyNumberTile with its ±. Every figure is READ from harness/fixture.ts (nothing is retyped here), so assertFixtureConsistency and the component's own kind guard both hold over it. Jacobs is out: he is in no ranking and appears once, below the lists, attributed and dated.">
        <PicksList {...PICKS_PROPS} />
      </Case>

      <Case id="picks-states" title="14 · SHIPPED PicksList — empty state and the cap"
        note="Two states the shipped sites will hit. Left: a category with no rows renders the existing 'No pick yet' vocabulary rather than a fabricated zero, bar or tile. Right: a four-player category renders THREE — the cap is a ceiling, and the first three are shown, not the last three.">
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <InstantHead>Empty category</InstantHead>
            <PicksList categories={[{ category: "Anytime TD", rows: [] }]} />
          </div>
          <div className="flex flex-col gap-2">
            <InstantHead>Four rows in, three rendered</InstantHead>
            <PicksList
              categories={[
                {
                  category: "Anytime TD",
                  rows: [
                    { key: "td:jacobs", name: PLAYERS.jacobs.name, team: PLAYERS.jacobs.team, detail: "Anytime TD", value: 0.41, kind: "probability", provenance: "not shown — outside the cap" },
                    { key: "td:robinson", name: PLAYERS.robinson.name, team: PLAYERS.robinson.team, detail: "Anytime TD", value: 0.38, kind: "probability", provenance: "model 38% · bucket hits 33% · n=140" },
                    { key: "td:wilson", name: PLAYERS.wilson.name, team: PLAYERS.wilson.team, detail: "Anytime TD", value: 0.24, kind: "probability", provenance: "model 24% · bucket hits 24% · n=98" },
                    { key: "td:love", name: PLAYERS.love.name, team: PLAYERS.love.team, detail: "Anytime TD", value: 0.22, kind: "probability", provenance: "model 22% · bucket hits 24% · n=98" },
                  ],
                },
              ]}
            />
          </div>
        </div>
      </Case>

      <Case id="picks-detail" title="15 · SHIPPED PicksList — a row's own detail, and the rule that draws it"
        note="Four states of ONE rule, on Sports_Predictor's REAL heading/detail pairs copied from origin/main src/lib/picksPanel.ts. A row draws its detail only when it is a PROBABILITY row whose detail adds a word the heading does not carry. TOP is the new market: 'QB passing TDs' rows are kind probability with detail 'Over 2.5', so each reads 'Over 2.5 · model line' beside 64% instead of a bare percentage with no line. MIDDLE is picksPanel.ts:79, the case review found: heading 'QB passing yards', detail 'Pass yds', kind projection — an ABBREVIATED restatement whose words share no token with the heading, so a word-compare alone drew it and appended ' · model call' to a yardage estimate. Nothing is drawn now, and no projection row is ever labelled a call. THIRD is picksPanel.ts:256: a probability row whose detail IS the heading, which the kind gate cannot catch and only the word-compare can. BOTTOM is an empty list, which renders nothing at all — not the title, not a zero. The same rows are pinned as tests in src/components/sportsPayloads.test.tsx; these are the pixels.">
        <div className="flex flex-col gap-6">
          <div data-shot="qb-passing-tds" className="flex flex-col gap-2">
            <InstantHead>QB passing TDs — probability row, the detail is the call</InstantHead>
            <PicksList categories={[QB_PASSING_TD_CATEGORY]} />
          </div>
          <div data-shot="no-duplication" className="flex flex-col gap-2">
            <InstantHead>QB passing yards — projection row, abbreviated restatement, nothing drawn</InstantHead>
            <PicksList categories={[QB_PASSING_YARDS_CATEGORY]} />
          </div>
          <div data-shot="detail-equals-heading" className="flex flex-col gap-2">
            <InstantHead>Rush or receiving TD — probability row whose detail IS the heading</InstantHead>
            <PicksList categories={[NFL_TD_CATEGORY]} />
          </div>
          <div data-shot="empty-list" className="flex flex-col gap-2">
            <InstantHead>An empty list</InstantHead>
            {/* Nothing follows this line but the note. `categories={[]}` returns
                null, so there is no title, no panel and no figure to screenshot;
                the label above is what a screenshot of "nothing" needs beside it
                to be readable as a state rather than as a broken page. */}
            <PicksList categories={[]} />
            <p className="text-xs text-pr-text-faint">
              ↑ nothing rendered. Not the title, not an empty card, not a 0%.
            </p>
          </div>
        </div>
      </Case>

      <Case id="signals" title="16 · SHIPPED SignalRows — the shared contract, every state"
        note="src/components/SignalRows.tsx, the real component on the fixture's own signals. One compact row per finding: a headline of at most 12 words and a collapsed evidence line carrying n, the date and the source. The chip is neutral on purpose — a disagreement with the line is not an outcome, so it is never green. Every figure is read from harness/fixture.ts (the gap is FIX.edgePts, the rate is BUCKET.hits / BUCKET.n), so a signal mock cannot disagree with the tiles about the same game; fixture.test.ts holds that.">
        <div className="flex flex-col gap-6">
          <div data-shot="signals-populated" className="flex flex-col gap-2">
            <InstantHead>Populated — both visuals, evidence collapsed</InstantHead>
            <SignalRows signals={SIGNALS} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              Two rows, in the order the endpoint ranked them by <code>strength</code>. The bar is the
              trust row&apos;s rate ({Math.round(trustRate * 100)}% of {BUCKET.n} games); the chip is
              the gap ({FIX.edgePts} pts) with the sign in the figure, not in the colour.
            </p>
          </div>

          <div data-shot="signals-absence" className="flex flex-col gap-2">
            <InstantHead>Absence — the player&apos;s own projection, in the sport&apos;s units</InstantHead>
            <SignalRows signals={[ABSENCE_SIGNAL, PL_ABSENCE_SIGNAL]} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              Phase 2&apos;s visual, and the one this package used to REFUSE — which is
              why no absence signal could be drawn anywhere until it landed. The
              marker is a plain unsigned number, because the component cannot know
              the unit: NFL&apos;s is 78 <em>rush yards</em> and PL&apos;s is a share, and only the
              adapter knows which. It is deliberately not a bar (a projection is not
              a hit rate) and deliberately not coloured: a player being out is not an
              outcome the model got right or wrong. Its <code>n</code> counts injured
              players, so the <code>n ≥ {SPEC_MIN_N}</code> rate floor is exempt —
              both rows above draw at n=3 and n=1.
            </p>
          </div>

          <div data-shot="signals-empty" className="flex flex-col gap-2">
            <InstantHead>Empty list</InstantHead>
            {/* Nothing follows this line but the note. `signals={[]}` returns null,
                so there is no heading, no panel and no figure — not even a "no
                signals" line, which would be an empty state and spec §2 rules
                those out. */}
            <SignalRows signals={[]} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              ↑ nothing rendered. Not the heading, not an empty card, not a 0%.
            </p>
          </div>

          <div data-shot="signals-below-floor" className="flex flex-col gap-2">
            <InstantHead>A rate below the floor (n={BELOW_FLOOR_SIGNAL.n}, floor {SPEC_MIN_N})</InstantHead>
            {/* The trust row with n under the floor and nothing else changed. The
                WHOLE row goes, not just the bar: a headline reading "has been
                right 67% of the time" with the n and the bar removed is a worse
                row than no row, and spec §4 says "below that the row says
                nothing". */}
            <SignalRows signals={[BELOW_FLOOR_SIGNAL]} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              ↑ nothing rendered. The populated case above with{" "}
              <code>n = {BELOW_FLOOR_SIGNAL.n}</code> instead of {BUCKET.n} would have drawn a{" "}
              {Math.round(BELOW_FLOOR_SIGNAL.headline.figures.rate * 100)}% bar under 12 games — which is
              the rate from a handful of games that spec §4 forbids.
            </p>
          </div>

          <div data-shot="signals-evidence-open" className="flex flex-col gap-2">
            <InstantHead>Evidence expanded — n and date always, source revealed, by keyboard</InstantHead>
            {/* The disclosure below opens itself on mount with a real click on a
                real button, which is the same event a keyboard Enter produces —
                the shot script does not reach in, so the captured state is one a
                reader reached rather than one a harness forced into the DOM. The
                `aria-expanded` and the keyboard path are asserted in
                src/components/SignalRows.test.tsx. */}
            <OpenEvidence signals={SIGNALS} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              <code>n</code> and the date are in the row without opening anything; the control reveals{" "}
              <code>source</code>, the one field long enough to be why the line collapses at 390px. It is a
              real button carrying <code>aria-expanded</code>, so it is reachable by Tab and Enter with no
              pointer — pinned by a test that tabs to it and presses Enter rather than clicking.
            </p>
          </div>

          <div data-shot="signals-long-headline" className="flex flex-col gap-2">
            <InstantHead>A headline over {MAX_HEADLINE_WORDS} words — clipped, not refused</InstantHead>
            <SignalRows signals={[LONG_HEADLINE_SIGNAL]} />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              Clipping keeps the first 12 ordinary words PLUS every word stating a drawn figure, so
              the {Math.round(trustRate * 100)}% survives and the bar below still draws the same{" "}
              {Math.round(trustRate * 100)}% the populated case does. A plain 12-word clip would cut
              here and leave a bar under words that no longer mention it — the honesty rule broken by
              the cap that enforces §6. The cap is therefore on the sentence AROUND the figure: a
              clipped row can run past 12 words, and the fix for that is the adapter&apos;s shorter
              wording, not a longer row.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <InstantHead>Not drawable yet — refused, not silently dropped</InstantHead>
            <RefusedVisual />
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              Phase 2&apos;s <code>absence_strip</code> and phase 3&apos;s <code>projected_vs_actual</code>{" "}
              are in the type and are not drawable yet. Rendering the words without the marker is a
              defect no test and no screenshot of a correct-looking row would catch, so the component
              throws a named error instead.
            </p>
          </div>
        </div>
      </Case>

      <Case id="boxfilter" title="10 · box score split by team — Away / Both / Home (proposal)"
        note="Phase 0 (Sports PR #20, in review): group by team then position, team totals once, default Both. Real BoxScore component, mock groups.">
        <Proposal label="team filter">
          <div className="flex gap-1" role="group" aria-label="Team filter">
            {["Away", "Both", "Home"].map((t) => (
              <button key={t} type="button" aria-pressed={t === "Both"}
                className={`rounded-pr border px-3 py-1 font-pr-display text-xs font-semibold uppercase tracking-wide ${t === "Both" ? "border-pr-accent bg-pr-accent text-pr-accent-ink" : "border-pr-rule text-pr-text-dim"}`}>
                {t}
              </button>
            ))}
          </div>
          <BoxScore columns={BOX_COLUMNS} groups={BOX_GROUPS_BOTH} title="Predicted box score · RB" />
        </Proposal>
      </Case>
    <Case id="instant-nfl" title="11 · the shipped block — NFL, full (InstantBlock)"
        note="The real component, the site's own bundle and extras: timing chip, verdict, tiles, bar, record. No request, no state, no effect — the case above and this one read the same figures from the same object.">
        <InstantBlock
          sport="nfl"
          bundle={NFL_BUNDLE}
          extras={{
            tiles: NFL_TILES,
            segments: NFL_SEGMENTS,
            record: { label: "Picks made before kickoff", hits: FIX.recordHits, settled: FIX.recordSettled },
          }}
        />
      </Case>

      <Case id="instant-f1" title="12 · the shipped block — F1, reduced (InstantBlock)"
        note="Same component, no extras beyond the record: F1 draws no tiles and no bar (decision 8 keeps its insight per-race). The unverified badge is the honest reading when the schedule carried no session start.">
        <InstantBlock
          sport="f1"
          bundle={F1_BUNDLE}
          extras={{ record: { label: "Picks made before the session", hits: 9, settled: 14 } }}
        />
      </Case>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
