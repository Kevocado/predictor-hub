import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { contrast } from "./contrast";

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
});

describe("contrast", () => {
  it("matches WCAG reference values", () => {
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 1);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});
