/**
 * The phone check jsdom can actually make.
 *
 * jsdom does not lay out, so it cannot measure a scrollWidth. What it can do is
 * assert the invariant that keeps the page from growing wider than the screen:
 * the tab bar contains its own overflow, and nothing in the kit is pinned to a
 * fixed pixel width that a 375px viewport cannot hold. The rendered truth is the
 * batched 375px screenshot; this is the regression guard that runs on every
 * commit.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CalibrationChart } from "./CalibrationChart";
import { HowCounted } from "./HowCounted";
import { HubTabs } from "./HubTabs";
import { RecentPicks } from "./RecentPicks";
import { RecordBlock } from "./RecordBlock";
import { RecordHeadline } from "./RecordHeadline";
import { WeekStrip } from "./WeekStrip";
import type { RecordModel } from "./types";

const MODEL: RecordModel = {
  lead: "game_outcome",
  headline: "counted",
  markets: [
    { key: "game_outcome", label: "Winner pick", counted: { correct: 25, n: 52 }, preKickoff: { correct: 20, n: 40 } },
  ],
  weeks: [{ weekStart: "2026-09-01", n: 10, correct: 6, tracked: true }],
  calibration: [{ key: "game_outcome", label: "Winner pick", buckets: [{ bucket: "50-60%", n: 10, correct: 6 }] }],
  recent: [{ id: "a", label: "Winner pick", pick: "Boston", actual: "Boston", hit: true, when: "Mon 5 Oct", madeBeforeKickoff: true }],
};

const TABS = ["Games", "Teams", "Players", "Rankings", "Track record"].map((label, i) => ({ id: `t${i}`, label }));

describe("at 375px", () => {
  it("the tab bar contains its own overflow instead of widening the page", () => {
    render(
      <div style={{ width: 375 }}>
        <HubTabs tabs={TABS} active="t0" onChange={() => {}} panels={{}} />
      </div>,
    );
    const list = screen.getByRole("tablist");
    expect(list.className, "the tablist must be the scroll container").toMatch(/overflow-x-auto/);
    expect(list.getAttribute("style") ?? "", "no inline width on the scroller").not.toMatch(/width/);
  });

  it("nothing in the kit is pinned to a fixed pixel width", () => {
    const { container } = render(
      <div>
        <RecordBlock id="tr" title="Counted record">
          <RecordHeadline markets={MODEL.markets} mode="counted" lead="game_outcome" />
        </RecordBlock>
        <WeekStrip weeks={MODEL.weeks!} />
        <CalibrationChart series={MODEL.calibration!} />
        <RecentPicks picks={MODEL.recent!} />
        <HowCounted moment="kickoff" headline="counted" />
      </div>,
    );
    for (const el of container.querySelectorAll("[style]")) {
      expect(
        el.getAttribute("style")!,
        "a fixed px width is what pushes a 375px page sideways",
      ).not.toMatch(/(min-)?width:\s*\d+px/);
    }
  });
});
