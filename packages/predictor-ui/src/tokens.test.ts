import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { contrast } from "./contrast";
import { PANEL } from "./components/ProbabilityBar";

// jsdom rewrites import.meta.url, so resolve from the package root instead.
const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8");

// Collect `--color-pr-*: #hex` declarations per scope: the @theme base, then
// each [data-sport="…"] override block.
function scope(selector: RegExp): Record<string, string> {
  const block = selector.exec(css)?.[1] ?? "";
  return Object.fromEntries([...block.matchAll(/--color-pr-([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}

const base = scope(/@theme\s*\{([^}]*)\}/);
const sports = ["pl", "f1", "nfl", "cfb", "nba", "hub"] as const;

describe("tokens", () => {
  it("defines every neutral, status and accent token", () => {
    for (const k of ["stage", "panel", "panel-2", "rule", "text", "text-dim", "text-faint", "accent", "accent-ink", "win", "loss", "lean"]) {
      expect(base[k], k).toMatch(/^#/);
    }
  });

  it("keeps every text colour at 4.5:1 or more on the stage and both panels", () => {
    for (const surface of ["stage", "panel", "panel-2"]) {
      for (const text of ["text", "text-dim", "text-faint", "win", "loss", "lean"]) {
        expect(contrast(base[text], base[surface]), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("gives every sport an accent that reads on the stage and ink that reads on the accent", () => {
    for (const sport of sports) {
      const s = { ...base, ...scope(new RegExp(`\\[data-sport="${sport}"\\]\\s*\\{([^}]*)\\}`)) };
      expect(css, `missing scope for ${sport}`).toContain(`[data-sport="${sport}"]`);
      expect(contrast(s.accent, s.stage), `${sport} accent on stage`).toBeGreaterThanOrEqual(3);
      expect(contrast(s.accent, s.panel), `${sport} accent on panel`).toBeGreaterThanOrEqual(3);
      expect(contrast(s["accent-ink"], s.accent), `${sport} ink on accent`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("uses the Barlow family and no Inter", () => {
    expect(css).toMatch(/--font-pr-display:\s*"Barlow Condensed"/);
    expect(css).toMatch(/--font-pr-body:\s*"Barlow"/);
    expect(css).not.toMatch(/Inter/);
  });

  it("keeps the bar's neutral ramp three steps deep and in order", () => {
    // ProbabilityBar paints a segment that is not the pick from this ramp, and
    // a three-way market has three segments. Two steps would make the draw the
    // same grey as one of the sides, which is the failure this ramp exists to
    // prevent — so the order and the depth are both pinned.
    const ramp = ["text-dim", "text-faint", "fill-mute"].map((k) => contrast(base[k], base.panel));
    for (const [i, ratio] of ramp.entries()) {
      expect(ratio, `ramp step ${i} on panel`).toBeGreaterThanOrEqual(1.6);
      if (i) expect(ratio, `ramp step ${i} is quieter than ${i - 1}`).toBeLessThan(ramp[i - 1]);
    }
  });

  it("holds the fill tone to the fill bar, not the text bar, and says so", () => {
    // `--color-pr-fill-mute` paints a bar segment; it is not a text colour, so
    // the 4.5:1 gate above does not apply to it and adding it to that list's
    // `text` entries would fail. It sits in the same 3:1 band the spec already
    // sets for a sport accent on the panel, so it is unmistakably visible
    // without being the brightest thing in the component.
    expect(contrast(base["fill-mute"], base.panel)).toBeGreaterThanOrEqual(3);
    expect(contrast(base["fill-mute"], base.panel)).toBeLessThan(4.5);
    // And the name says what it paints, so nobody reaches for it as a text colour.
    expect(css).not.toMatch(/--color-pr-text-mute/);
  });
});

describe("review fixes", () => {
  it("keeps focus visible on the notched card (clip-path would cut an outside outline)", () => {
    expect(css).toMatch(/\.pr-notch:focus-visible\s*\{[^}]*outline-offset:\s*-\d+px/);
  });
  it("loads fonts from fonts.css (imported before tailwindcss), never from tokens.css", () => {
    const fonts = readFileSync(resolve(__dirname, "fonts.css"), "utf8");
    expect(css).not.toMatch(/@import\s+url/);
    expect(fonts).toMatch(/@import url\("https:\/\/fonts\.googleapis\.com\/css2\?family=Barlow/);
  });
  it("tells the browser the pages are dark", () => {
    expect(css).toMatch(/color-scheme:\s*dark/);
  });
  it("fails on any colour token it cannot check", () => {
    const declared = [...css.matchAll(/--color-pr-[\w-]+:\s*([^;]+);/g)].map((m) => m[1].trim());
    for (const value of declared) expect(value, value).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
  it("the bar's panel constant matches the panel token", () => {
    expect(PANEL.toLowerCase()).toBe(base.panel.toLowerCase());
  });
});

describe("contrast", () => {
  it("matches WCAG reference values", () => {
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 1);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});

describe("rank tier tokens", () => {
  // Dark theme (base @theme)
  const dark = {
    stage: base.stage,
    panel: base.panel,
    text: base.text,
    "rank-good-bg": base["rank-good-bg"],
    "rank-good-ink": base["rank-good-ink"],
    "rank-mid-bg": base["rank-mid-bg"],
    "rank-mid-ink": base["rank-mid-ink"],
    "rank-bad-bg": base["rank-bad-bg"],
    "rank-bad-ink": base["rank-bad-ink"],
  };

  // Light theme ([data-theme="light"])
  const lightScope = scope(/\[data-theme="light"\]\s*\{([^}]*)\}/);
  const light = {
    stage: lightScope.stage,
    panel: lightScope.panel,
    text: lightScope.text,
    "rank-good-bg": lightScope["rank-good-bg"],
    "rank-good-ink": lightScope["rank-good-ink"],
    "rank-mid-bg": lightScope["rank-mid-bg"],
    "rank-mid-ink": lightScope["rank-mid-ink"],
    "rank-bad-bg": lightScope["rank-bad-bg"],
    "rank-bad-ink": lightScope["rank-bad-ink"],
  };

  for (const [themeName, theme] of [["dark", dark], ["light", light]] as const) {
    // Type assertion to allow string indexing
    const t = theme as Record<string, string>;
    describe(`${themeName} theme`, () => {
      it("has all rank tier bg/ink tokens defined", () => {
        for (const k of ["rank-good-bg", "rank-good-ink", "rank-mid-bg", "rank-mid-ink", "rank-bad-bg", "rank-bad-ink"]) {
          expect(t[k], k).toMatch(/^#/);
        }
      });

      it("every tier bg/ink pair meets 4.5:1 contrast", () => {
        for (const tier of ["good", "mid", "bad"] as const) {
          const bg = t[`rank-${tier}-bg`];
          const ink = t[`rank-${tier}-ink`];
          const ratio = contrast(ink, bg);
          expect(ratio, `${tier} ink on bg (${themeName})`).toBeGreaterThanOrEqual(4.5);
        }
      });

      it("every tier bg meets 4.5:1 on stage and panel with default text", () => {
        for (const surface of ["stage", "panel"] as const) {
          for (const tier of ["good", "mid", "bad"] as const) {
            const bg = t[`rank-${tier}-bg`];
            const ratio = contrast(t.text, bg);
            expect(ratio, `${tier} bg on ${surface} (${themeName})`).toBeGreaterThanOrEqual(4.5);
          }
        }
      });
    });
  }
});
