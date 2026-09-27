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
import { ExplainerPanel, KeyNumberTile, RecordStrip, FactorList, ProbabilityBar } from "../src/index";
import type { Explanation, MarketTile, Segment } from "../src/index";

const NFL_PICK = 0.62;
const NFL_VERDICT: Explanation = {
  verdict: "Baltimore is the pick, but the line is thinner than the number.",
  band: "strong", // computed: 0.62 on a two-way market is >= 0.60 (13a)
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans Baltimore",
      text: "The rating gap has held all week and the model has not moved off it." },
    { key: "spread", direction: "down", headline: "The line asks more than the margin",
      text: "The market is asking for more than the model thinks the gap is worth." },
  ],
  source: "llm", model: "nemotron-3.5-lightning",
  generated_at: new Date(Date.now() - 120_000).toISOString(),
  sport: "nfl", pick_timing: "pre_kickoff",
};

// §7a, with the record in the bottom strip rather than as a fourth tile — §6
// lists it as an extra, and the mock's tile duplicates it.
const NFL_TILES: MarketTile[] = [
  { market: "moneyline", label: "moneyline", value: "62%", sub: "win · BAL" },
  { market: "spread", label: "spread", value: "BAL −2.5", sub: "model −3.4" },
  { market: "total", label: "total", value: "45.2", sub: "total pts · line 44.5" },
];
const NFL_SEGMENTS: Segment[] = [
  { label: "KC", prob: 0.38, market: "moneyline" },
  { label: "BAL", prob: NFL_PICK, market: "moneyline" },
];

const PL_VERDICT: Explanation = {
  verdict: "Arsenal are the pick, and the market roughly agrees.",
  band: "moderate", // computed: 0.48 on a three-way market is < 0.50 (13a)
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
const PL_TILES: MarketTile[] = [
  { market: "result", label: "result", value: "48%", sub: "Arsenal win" },
  { market: "total_goals", label: "total goals", value: "2.7", sub: "O2.5 56%" },
  { market: "btts", label: "both score", value: "61%", sub: "btts" },
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
        note="The same bar with a complete implied. The comparison is only drawn when it covers every outcome above it.">
        <div data-sport="pl" className="max-w-[46rem]">
          <ProbabilityBar segments={PL_SEGMENTS} legend={PL_LEGEND_COMPLETE} minSegmentPx={2} />
        </div>
      </Case>

      <Case id="sliver" title="4 · a 3% segment" note="min-width 2px, and the label never shrinks below the 12px floor.">
        <div className="max-w-[46rem]"><ProbabilityBar segments={SLIVER} minSegmentPx={2} /></div>
      </Case>

      <Case id="rebuilt" title="5 · a rebuilt pick" note="Shown, never counted, never graded.">
        <div className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={{ ...NFL_VERDICT, pick_timing: "rebuilt" }}
            tiles={NFL_TILES} segments={NFL_SEGMENTS} />
        </div>
      </Case>

      <Case id="no-pick" title="6 · no pick" note="The weakest band, because there is no confidence to claim.">
        <div className="max-w-[46rem]">
          <ExplainerPanel {...RESTING} data={{
            verdict: "There is no pick for this one yet.", band: "leaning",
            factors: [
              { key: "moneyline", direction: "up", headline: "The model likes the favourite", text: "Its numbers favour KC over BAL." },
              { key: "record", direction: "up", headline: "Its record so far", text: "Counted from picks made before the start." },
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
            <KeyNumberTile tile={{ market: "total", label: "total", value: "" }} />
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
