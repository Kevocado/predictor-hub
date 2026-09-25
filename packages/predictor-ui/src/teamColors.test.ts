import { describe, expect, it } from "vitest";
import { contrast, parseHex, readableChip } from "./contrast";

// Real primary colours across the five sports: bright, mid and very dark.
const TEAM_COLOURS = [
  "#E31837", "#241773", "#FFB612", "#311D00", "#002C5F", "#5A1414", "#0B2265", "#FB4F14", "#203731", "#69BE28",
  "#AA0000", "#F5B301", "#461D7C", "#BA0C2F", "#DA291C", "#6CABDD", "#034694", "#EF0107", "#132257", "#7A263A",
  "#E10600", "#27F4D2", "#FF8000", "#3671C6", "#CE1141", "#1D428A", "#00788C", "#FFFFFF", "#000000", "#777777",
];

describe("parseHex", () => {
  it("expands 3-digit hex and rejects anything that is not hex", () => {
    expect(parseHex("#fff")).toBe("#ffffff");
    expect(parseHex("#E31837")).toBe("#e31837");
    expect(parseHex("rgb(1,2,3)")).toBeNull();
    expect(parseHex("var(--x)")).toBeNull();
  });
});

describe("readableChip", () => {
  it.each(TEAM_COLOURS)("%s gets ink at 4.5:1 or better", (colour) => {
    const chip = readableChip(colour);
    expect(chip).not.toBeNull();
    expect(contrast(chip!.ink, chip!.fill)).toBeGreaterThanOrEqual(4.5);
  });
  it("keeps the team's own colour when it already reads", () => {
    expect(readableChip("#FFB612")!.fill).toBe("#ffb612");
  });
  it("gives no chip colour for values it cannot read", () => {
    expect(readableChip("rgb(1,2,3)")).toBeNull();
  });
});
