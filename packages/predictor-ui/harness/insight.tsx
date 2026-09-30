/**
 * Fixture-insight mocks for the 2026-09-30 spec — NOT a shipped surface.
 *
 * Review instrument only: the instant block is composed from the REAL
 * predictor-ui components (StatusBadge, KeyNumberTile, ProbabilityBar,
 * RecordStrip, BoxScore) with fixture-shaped data, so layout, tokens and
 * type carry over to implementation. The callout / player-pick / filter
 * pieces are static proposal markup (marked PROPOSAL): they show intent for
 * the spec's screenshots, not a component to import.
 */
import { createRoot } from "react-dom/client";
import {
  StatusBadge,
  KeyNumberTile,
  ProbabilityBar,
  RecordStrip,
  BoxScore,
  type MarketTile,
  type Segment,
  type BoxScoreGroup,
} from "../src/index";

const RESTING = { loading: false, error: false, onRetry: () => {} };
void RESTING;

// --- shared mock data -------------------------------------------------------

const NFL_TILES: MarketTile[] = [
  { market: "moneyline", label: "moneyline", value: "72%", sub: "win · GB" },
  { market: "spread", label: "spread", value: "GB -4.5", sub: "model GB -6.1" },
  { market: "total", label: "total", value: "42.1", sub: "total pts · line 43.5" },
];
const NFL_SEGMENTS: Segment[] = [
  { label: "GB", prob: 0.72, market: "moneyline" },
  { label: "ATL", prob: 0.28, market: "moneyline" },
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

const BOX_COLUMNS = [
  { key: "yds", label: "Yds" },
  { key: "td", label: "TD%" },
];
const BOX_GROUPS_BOTH: BoxScoreGroup[] = [
  {
    position: "GB · RB",
    rows: [
      { key: "jacobs", name: "J. Jacobs", position: "RB", team: "GB", order: 1, isStarter: true, values: [78, 41] },
      { key: "wilson", name: "E. Wilson", position: "RB", team: "GB", order: 2, isStarter: false, values: [22, 12] },
    ],
    subtotals: [{ label: "GB total", values: [100, null] }],
  },
  {
    position: "ATL · RB",
    rows: [
      { key: "robinson", name: "B. Robinson", position: "RB", team: "ATL", order: 1, isStarter: true, values: [84, 38] },
    ],
    subtotals: [{ label: "ATL total", values: [84, null] }],
  },
];

function App() {
  return (
    <main data-sport="nfl" className="min-h-screen bg-pr-stage font-pr-body text-pr-text">
      <Case id="nfl-rebuilt" title="1 · NFL rebuilt — the instant block"
        note="Before: badge, tiles, bar and verdict appeared only after pressing Get the AI summary. After: they render from the site bundle with no request. The flow sentences (Win probabilities…, The model picks…) and the Match Markets repeat are gone.">
        <div className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <StatusBadge status="rebuilt" moment="kickoff" />
            <span>This pick was made after the game started, so it is shown for reference and not counted.</span>
          </p>
          <Verdict>Green Bay is the pick, for reference.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NFL_SEGMENTS} minSegmentPx={2} pick={{ label: "GB" }} />
          <RecordStrip label="Picks made before kickoff" hits={11} settled={15} />
        </div>
      </Case>

      <Case id="nfl-pre" title="2 · NFL pre-kickoff — the instant block"
        note="The normal state needs no fanfare: a quiet timing chip, the verdict, tiles, bar, record. No button — there is nothing to wait for.">
        <div className="flex flex-col gap-3">
          <p className="flex max-w-[70ch] flex-wrap items-center gap-2 text-sm text-pr-text-dim">
            <span className="inline-flex items-center whitespace-nowrap rounded-pr border border-pr-rule px-1.5 py-0.5 font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-dim">
              Made before kickoff
            </span>
          </p>
          <Verdict>Green Bay is the pick.</Verdict>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
          </div>
          <ProbabilityBar segments={NFL_SEGMENTS} minSegmentPx={2} pick={{ label: "GB" }} />
          <RecordStrip label="Picks made before kickoff" hits={11} settled={15} />
        </div>
      </Case>

      <Case id="pl-pre" title="3 · PL pre-kickoff — three-way bar plus market row"
        note="The market's own row draws only because implied covers every outcome. Same instant block, three-way market.">
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

      <Case id="nba-now" title="5 · NBA — instant today, badge and verdict added"
        note="NBA already shows its numbers with no gate. The spec adds the verdict line and (once NBA tracks pre-tip picks) the timing badge — and nothing else changes.">
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
        note="Present: an attributed, dated flag that demotes the affected pick — never a recommendation of a player who is out. Absent: the block says nothing at all.">
        <div className="flex flex-col gap-3">
          <InstantHead>With news</InstantHead>
          <div className="flex items-start gap-3 rounded-pr border border-pr-rule bg-pr-panel px-3 py-2">
            <span className="shrink-0 rounded-pr px-2 py-1 font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-loss">
              Out
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <p className="text-sm font-medium leading-snug text-pr-text">J. Jacobs is out — the RB pick moves to E. Wilson.</p>
              <p className="text-xs text-pr-text-faint">Official injury report · GB · week 6 · via nfl_data_py</p>
            </div>
          </div>
          <InstantHead>Without news</InstantHead>
          <p className="max-w-[70ch] text-xs text-pr-text-faint">(no news element renders — the block says nothing)</p>
        </div>
      </Case>

      <Case id="callouts" title="8 · AI insight — callouts, not paragraphs (proposal)"
        note="Two scannable rows. Neither restates a tile: the first compares model against line (both figures are in the facts, the disagreement is the interpretation); the second is a trend with n. Anything without a fact behind it is rejected by the validator.">
        <Proposal label="insight callouts">
          <Callout delta="▲ 1.6 pts" deltaTone="text-pr-win"
            text="The model wants more than the market on Green Bay."
            evidence="Model GB −6.1 vs line GB −4.5 · last 10 GB covers: 7" />
          <Callout delta="7–3" deltaTone="text-pr-text-dim"
            text="Green Bay covers after rest: 7 of the last 10."
            evidence="Trend over the stored pre-kickoff record · n=10" />
        </Proposal>
      </Case>

      <Case id="picks" title="9 · best player picks — model output with its record (proposal)"
        note="Ranked by the model's own number. Every row carries provenance: a graded hit rate where a ledger exists, an explicit ungraded note where none does. Never wagering advice.">
        <Proposal label="player picks">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[30rem] border-collapse text-sm">
              <thead>
                <tr className="text-left font-pr-display text-xs uppercase tracking-wide text-pr-text-dim">
                  <th className="py-1 pr-3 font-semibold">Player</th>
                  <th className="py-1 pr-3 font-semibold">Market</th>
                  <th className="py-1 pr-3 font-semibold">Model</th>
                  <th className="py-1 font-semibold">Record</th>
                </tr>
              </thead>
              <tbody className="text-pr-text">
                <tr className="border-t border-pr-rule">
                  <td className="py-1.5 pr-3">B. Saka (ARS)</td>
                  <td className="py-1.5 pr-3">Anytime goal</td>
                  <td className="py-1.5 pr-3 tabular-nums">34%</td>
                  <td className="py-1.5 text-pr-text-dim">hits 31% when called · n=58</td>
                </tr>
                <tr className="border-t border-pr-rule">
                  <td className="py-1.5 pr-3">J. Jacobs (GB)</td>
                  <td className="py-1.5 pr-3">Anytime TD</td>
                  <td className="py-1.5 pr-3 tabular-nums">41%</td>
                  <td className="py-1.5 text-pr-text-dim">bucket 40–50%: hits 44% · n=112</td>
                </tr>
                <tr className="border-t border-pr-rule">
                  <td className="py-1.5 pr-3">J. Tatum (BOS)</td>
                  <td className="py-1.5 pr-3">Points</td>
                  <td className="py-1.5 pr-3 tabular-nums">27.4 proj.</td>
                  <td className="py-1.5 text-pr-text-dim">no graded record yet</td>
                </tr>
                <tr className="border-t border-pr-rule">
                  <td className="py-1.5 pr-3">D. Edwards (UGA)</td>
                  <td className="py-1.5 pr-3">Rush yds</td>
                  <td className="py-1.5 pr-3 tabular-nums">96 proj.</td>
                  <td className="py-1.5 text-pr-text-dim">no availability check (CFB)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Proposal>
      </Case>

      <Case id="boxfilter" title="10 · box score split by team — Away / Both / Home (proposal)"
        note="The preceding small PR: group by team then position, team totals once, default Both. Real BoxScore component, mock groups.">
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
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
