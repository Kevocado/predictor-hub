/**
 * The shared Track Record kit, every block, rendered from the real components
 * and tokens.
 *
 * This is the review instrument for Phase 1: the jsdom tests assert structure,
 * roles and the arithmetic, and they cannot tell whether the headline *reads*,
 * whether the week cells are legible, or whether the tab bar clips at 375px.
 * Those are judgements about pixels, so they are made about pixels — from this
 * page, in a browser, with the screenshots in the PR as the record.
 *
 * The fixture is the one `trackRecord.test.tsx` uses, so a mock and a render
 * cannot disagree about what the kit is being asked to draw. Data is the
 * hypothetical NFL record at the point the copy was written.
 */
import { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CalibrationChart,
  HowCounted,
  HubTabs,
  RecentPicks,
  RecordBlock,
  RecordHeadline,
  WeekStrip,
  type RecordModel,
} from "../src/index";

const MODEL: RecordModel = {
  lead: "game_outcome",
  headline: "counted",
  markets: [
    { key: "game_outcome", label: "Moneyline", counted: { correct: 25, n: 52 }, preKickoff: { correct: 20, n: 40 } },
    { key: "spread", label: "Spread", counted: { correct: 18, n: 40 }, preKickoff: { correct: 15, n: 33 } },
    { key: "total", label: "Total", counted: { correct: 14, n: 31 }, preKickoff: { correct: 12, n: 27 } },
    { key: "player_props", label: "Props", counted: { correct: 9, n: 24 }, preKickoff: { correct: 7, n: 19 } },
  ],
  weeks: [
    { weekStart: "2026-09-01", n: 12, correct: 8, tracked: true },
    { weekStart: "2026-09-08", n: 9, correct: 4, tracked: true },
    { weekStart: "2026-09-15", n: 14, correct: 9, tracked: true },
    { weekStart: "2026-09-22", n: 11, correct: 5, tracked: true },
    { weekStart: "2026-09-29", n: 6, correct: 4, tracked: true },
  ],
  calibration: [
    {
      key: "game_outcome",
      label: "Moneyline",
      buckets: [
        { bucket: "50-60%", n: 18, correct: 11 },
        { bucket: "60-70%", n: 12, correct: 8 },
        { bucket: "70%+", n: 7, correct: 6 },
      ],
    },
    {
      key: "spread",
      label: "Spread",
      buckets: [
        { bucket: "50-60%", n: 14, correct: 7 },
        { bucket: "60-70%", n: 6, correct: 3 },
      ],
    },
  ],
  recent: [
    { id: "1", label: "Moneyline", pick: "Kansas City", actual: "Kansas City", hit: true, when: "Sun 12 Oct", madeBeforeKickoff: true },
    { id: "2", label: "Spread", pick: "Buffalo −2.5", actual: "Buffalo", hit: false, when: "Sun 12 Oct", madeBeforeKickoff: true },
    { id: "3", label: "Total", pick: "Over 44.5", actual: "41 points", hit: false, when: "Sat 11 Oct", madeBeforeKickoff: false },
    { id: "4", label: "Moneyline", pick: "Philadelphia", actual: "Philadelphia", hit: true, when: "Sun 5 Oct", madeBeforeKickoff: true },
    { id: "5", label: "Spread", pick: "Detroit +1.5", actual: "Detroit", hit: null, when: "Sun 5 Oct", madeBeforeKickoff: true },
  ],
};

const TABS = [
  { id: "games", label: "Games" },
  { id: "teams", label: "Teams" },
  { id: "players", label: "Players" },
  { id: "standings", label: "Standings" },
  { id: "track-record", label: "Track record" },
];

function Page() {
  const [tab, setTab] = useState("track-record");
  return (
    <div data-sport="nfl" className="min-h-screen">
      <main className="mx-auto flex max-w-screen-xl flex-col gap-6 px-4 py-6 sm:px-6">
        <HubTabs tabs={TABS} active={tab} onChange={setTab} label="Pages" panels={{}} />
        <RecordBlock
          id="tr-record"
          title="The record, every counted pick"
          caption="Every recorded pick counts, once per game and market. The figure beside each rate is the subset made before kickoff."
        >
          <RecordHeadline markets={MODEL.markets} mode={MODEL.headline} lead={MODEL.lead} moment="kickoff" />
        </RecordBlock>
        <div className="grid gap-8 lg:grid-cols-2">
          <RecordBlock id="tr-week" title="Week by week">
            <WeekStrip weeks={MODEL.weeks!} />
          </RecordBlock>
          <RecordBlock id="tr-calibration" title="Does 70% mean 70%?">
            <CalibrationChart series={MODEL.calibration!} />
          </RecordBlock>
        </div>
        <RecordBlock id="tr-recent" title="Latest counted picks">
          <RecentPicks picks={MODEL.recent!} moment="kickoff" />
        </RecordBlock>
        <HowCounted moment="kickoff" headline={MODEL.headline} />
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Page />);
