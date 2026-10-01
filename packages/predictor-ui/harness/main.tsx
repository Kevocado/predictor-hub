/**
 * Every state the panel can be in, rendered from the real components and the
 * real tokens.
 *
 * This exists because the tests cannot do the one thing that matters most here:
 * a test can prove a proportion is `62%` and that it is in the accessible name,
 * and it still cannot tell you the bar *reads* as 62/38, that the chip does not
 * shout, or that a 3% sliver is visible rather than theoretical. Those are
 * judgements about pixels, so they are made about pixels — from this page, in a
 * browser, with the screenshots in the PR as the record.
 *
 * Each state carries the §7 mock's own facts, so a mock and a render cannot
 * disagree about what the panel is being asked to draw.
 */
import { createRoot } from "react-dom/client";
import { ExplainerPanel, KeyNumberTile, RecordStrip, FactorList, ProbabilityBar, pct } from "../src/index";
import type { Common, MarketTile, PickRef, Segment, Verdict } from "../src/index";

const NFL_PICK = 0.62;
// Annotated `Common & Verdict` — the v2 arm — rather than `Explanation`. On the
// union `.factors` does not exist, so the fixture could not hand its own factors
// to the standalone FactorList in state 9, and a v2 answer built here had to be
// typed as "either shape" to be passed to the panel at all. Naming the arm says
// what the fixture is, and it makes a fixture that is NOT a v2 answer fail to
// compile instead of quietly losing its factors.
const NFL_VERDICT: Common & Verdict = {
  verdict: "Baltimore is the pick, but the line is thinner than the number.",
  band: "strong", // computed: 0.62 on a two-way market is >= 0.60 (13a)
  // The pick travels with the answer (spec §5b) and the bar follows it by label.
  // It is the SECOND segment here, because the away side is listed first for US
  // sports — which is exactly the case an index-driven bar got wrong.
  pick: { label: "BAL" },
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans Baltimore",
      text: "The rating gap has held all week and the model has not moved off it." },
    { key: "spread", direction: "down", headline: "The line asks more than the margin",
      text: "The market is asking for more than the model thinks the gap is worth." },
    // A row that is a statement and not an argument. The service emits these
    // whether or not there is a pick — the record counts other picks, so it is
    // not evidence for this one (spec §5a) — and a neutral row draws no mark and
    // wears no win/loss colour, so this is the state a screenshot has to show.
    { key: "record", direction: "neutral", headline: "Its record so far",
      text: "41 of 68 picks made before kickoff have landed." },
  ],
  source: "llm", model: "nemotron-3.5-lightning",
  generated_at: new Date(Date.now() - 120_000).toISOString(),
  sport: "nfl", pick_timing: "pre_kickoff",
};

// §7a, with the record in the bottom strip rather than as a fourth tile — §6
// lists it as an extra, and the mock's tile duplicates it.
// Every `label` here is WORDS. `market` is the key the facts join on and the
// panel never prints it, so a tile whose label is the key again would put
// "moneyline" or "btts" in the one slot on a tile reserved for something a
// reader can read — and it would do it only when `sub` was absent, so the
// screenshot and the page could disagree about which tiles were affected.
const NFL_TILES: MarketTile[] = [
  { market: "moneyline", label: "Moneyline", value: "62%", sub: "win · BAL" },
  { market: "spread", label: "Spread", value: "BAL −2.5", sub: "model −3.4" },
  { market: "total", label: "Total points", value: "45.2", sub: "total pts · line 44.5" },
];
const NFL_SEGMENTS: Segment[] = [
  { label: "KC", prob: 0.38, market: "moneyline" },
  { label: "BAL", prob: NFL_PICK, market: "moneyline" },
];

/** PL's facts carry the pick's `side` as well as its label, so both travel, and
 *  the same value is handed to the bare bar in state 3 below. */
const PL_PICK: PickRef = { label: "Arsenal", side: "home" };

const PL_VERDICT: Common & Verdict = {
  verdict: "Arsenal are the pick, and the market roughly agrees.",
  band: "moderate", // computed: 0.48 on a three-way market is < 0.50 (13a)
  pick: PL_PICK,
  factors: [
    { key: "result", direction: "up", headline: "Model and market agree on Arsenal",
      text: "Both put Arsenal at about the same price, so there is no disagreement to exploit here." },
    { key: "total_goals", direction: "down", headline: "Goals look closer than the sides do",
      text: "The sides are near even, but the model expects goals." },
  ],
  source: "llm", model: "laguna-s-2.1",
  generated_at: new Date().toISOString(),
  sport: "pl", pick_timing: "pre_kickoff",
};
/** "Over 2.5 · 56%", not "O2.5 56%". Kevin read the old one as "02.5" from a
 *  screenshot, and the render settles it: Barlow's digit zero is a plain oval,
 *  not a slashed or dotted one, so a capital O and a zero are near-identical
 *  outlines and the only thing that ever told them apart was the space that was
 *  not there. The fix is the word — any character after the O kills it, and a
 *  separator alone would not, since the whole string is one run of glyphs. */
const PL_TILES: MarketTile[] = [
  { market: "result", label: "Match result", value: "48%", sub: "Arsenal win" },
  { market: "total_goals", label: "Total goals", value: "2.7", sub: "Over 2.5 · 56%" },
  // No `sub`: PL's `btts` facts carry a `yes_prob` and no market line, and §6
  // says an absent market renders nothing rather than a dash. So this tile falls
  // back to its label — which is the state a screenshot has to show, because it
  // is the state the `sub ?? market` bug printed "btts" into.
  { market: "btts", label: "Both teams score", value: "61%" },
];
const PL_SEGMENTS: Segment[] = [
  { label: "Arsenal", prob: 0.48, market: "result" },
  { label: "Draw", prob: 0.26, market: "result" },
  { label: "Chelsea", prob: 0.26, market: "result" },
];
// §13b: implied covers only the two sides, so the market row is OMITTED here and
// drawn in the next state instead. That difference is the point of this page.
const PL_LEGEND_PARTIAL: Segment[] = [
  { label: "Arsenal", prob: 0.44 },
  { label: "Chelsea", prob: 0.3 },
];
const PL_LEGEND_COMPLETE: Segment[] = [
  { label: "Arsenal", prob: 0.44 },
  { label: "Draw", prob: 0.25 },
  { label: "Chelsea", prob: 0.31 },
];

const SLIVER: Segment[] = [
  { label: "FAL", prob: 0.97, market: "moneyline" },
  { label: "DET", prob: 0.03, market: "moneyline" },
];

/** The sentence a no-pick panel uses to describe its own bar, computed from the
 *  bar's own segments.
 *
 *  It was typed by hand — "Its numbers favour KC over BAL" — beside a bar
 *  showing KC 38% and BAL 62%, which is what a screenshot caught: the sentence
 *  and the figure beside it disagreed, and nothing could tell. A hand-written
 *  sentence about a bar drifts the moment a number moves, so it is derived here
 *  from the same array the bar draws. This is fixture copy, not the product's:
 *  `template.py` has never written a "favour" row (with no pick it emits "Not
 *  much to go on" / "Where this stands"), so there is nothing in the service to
 *  derive it from. If the panel is ever to say this for real, the sentence
 *  belongs beside the other prose in the service, not in a renderer.
 */
function favours(segments: Segment[]): string {
  const [first, second] = [...segments].sort((a, b) => b.prob - a.prob);
  // The figures are derived too, not only the direction. Half a derivation still
  // leaves a sentence that can be right about which way and wrong about how far,
  // and the gap is the part a reader is most likely to check the bar for.
  return `Its numbers favour ${first.label} over ${second.label}, ${pct(first.prob)} to ${pct(second.prob)}.`;
}

const RESTING = { loading: false, error: false, onRetry: () => {} };

function Case({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="flex flex-col gap-2 border-t border-pr-rule p-5 first:border-t-0">
      <h2 className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-faint">{title}</h2>
      {note && <p className="-mt-1 max-w-[70ch] text-xs text-pr-text-faint">{note}</p>}
      {children}
    </section>
  );
}

function App() {
  return (
    <main data-sport="nfl" className="min-h-screen bg-pr-stage font-pr-body text-pr-text">
      <Case id="model-2way" title="1 · model answer, two-way market (NFL, §7a)">
        <div className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={NFL_VERDICT} tiles={NFL_TILES} segments={NFL_SEGMENTS}
            record={{ label: "Picks made before kickoff", hits: 41, settled: 68 }} />
        </div>
      </Case>

      <Case id="template-3way" title="2 · template answer, three-way market (PL, §7b)"
        note="No market row: implied covers only the two sides, so §13b omits it rather than drawing a comparison the reader cannot make.">
        <div data-sport="pl" className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={{ ...PL_VERDICT, source: "template", model: "" }}
            tiles={PL_TILES} segments={PL_SEGMENTS} legend={PL_LEGEND_PARTIAL}
            record={{ label: "Picks made before kickoff", hits: 38, settled: 71 }} />
        </div>
      </Case>

      <Case id="market-row-present" title="3 · the market row, when implied covers all three"
        note="The same bar with a complete implied, and the same pick. The comparison is only drawn when it covers every outcome above it. The lower row is the market's own figures: same columns, the market's numbers, at the same 12px as the model's.">
        <div data-sport="pl" className="flex max-w-[46rem] flex-col gap-4">
          <ProbabilityBar segments={PL_SEGMENTS} legend={PL_LEGEND_COMPLETE} minSegmentPx={2} pick={PL_PICK} />
          <div className="flex flex-col gap-1.5">
            <p className="max-w-[70ch] text-xs text-pr-text-faint">
              The same bar with <code className="text-pr-text-dim">expandable</code>, which is how a surface too narrow
              for a row of figures gets the fallback: a real <code className="text-pr-text-dim">aria-expanded</code>{" "}
              button that drops the market&rsquo;s figures and leaves the bar, rather than setting them below 12px.
            </p>
            <ProbabilityBar segments={PL_SEGMENTS} legend={PL_LEGEND_COMPLETE} minSegmentPx={2} pick={PL_PICK} expandable />
          </div>
        </div>
      </Case>

      <Case id="sliver" title="4 · a 3% segment" note="min-width 2px, and the label never shrinks below the 12px floor.">
        <div className="max-w-[46rem]"><ProbabilityBar segments={SLIVER} minSegmentPx={2} pick={{ label: "FAL" }} /></div>
      </Case>

      <Case id="rebuilt" title="5 · a pick made after the start" note="Counted, and labelled with the moment it was made — and no band, because a confidence word about a number produced once the answer was known asks the reader to resolve a contradiction this panel made (spec §13e).">
        <div className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={{ ...NFL_VERDICT, pick_timing: "rebuilt" }}
            tiles={NFL_TILES} segments={NFL_SEGMENTS} />
        </div>
      </Case>

      <Case id="no-pick" title="6 · no pick" note="No segment is accented, and no row is for or against anything. The band is still the weakest one, because there is no confidence to claim.">
        <div className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={{
            // No `pick` key at all, which is how the service says it: the answer
            // omits the key rather than sending a null for the panel to test.
            verdict: "There is no pick for this one yet.", band: "leaning",
            factors: [
              // Both neutral, as every factor is with no pick — the one beside the
              // bar was hand-written and said the opposite of the bar.
              { key: "moneyline", direction: "neutral", headline: "What the numbers say", text: favours(NFL_SEGMENTS) },
              { key: "record", direction: "neutral", headline: "Its record so far", text: "41 of 68 picks made before kickoff have landed." },
            ],
            source: "template", model: "", generated_at: new Date().toISOString(), sport: "nfl", pick_timing: "none",
          }} segments={NFL_SEGMENTS} />
        </div>
      </Case>

      <Case id="loading" title="7 · loading">
        <div className="max-w-[46rem]"><ExplainerPanel loading error={false} onRetry={() => {}} data={null} /></div>
      </Case>

      <Case id="error" title="8 · error">
        <div className="max-w-[46rem]"><ExplainerPanel loading={false} error onRetry={() => {}} data={null} /></div>
      </Case>

      <Case id="parts" title="9 · the parts alone" note="Tile, strip and factor list, so each is judged on its own rather than through the panel.">
        <div className="flex max-w-[46rem] flex-col gap-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {NFL_TILES.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
            <KeyNumberTile tile={{ market: "total", label: "Total points", value: "" }} />
          </div>
          <RecordStrip label="Picks made before kickoff" hits={41} settled={68} />
          <RecordStrip label="Nothing settled yet" hits={0} settled={0} />
          <FactorList factors={NFL_VERDICT.factors} onSelect={() => {}} expandable />
        </div>
      </Case>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
