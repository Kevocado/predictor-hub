/**
 * The browser surfaces: the parts of the page nobody drew, which ship with
 * defaults belonging to no design system.
 *
 * A scrollbar, a text caret and a focus ring are the three a user touches on
 * every single page, and every one of them defaults to a colour chosen by the
 * operating system. That is the cheapest signal that a page was assembled rather
 * than built — and the one that is skipped most reliably, because none of it is
 * visible in a component screenshot until someone drags a scrollbar.
 *
 * **Two of these were already done** — `::selection`, `:focus-visible` and
 * `font-variant-numeric` are in `tokens.css` today, so the backlog note that
 * asked for them was stale. What is missing, measured across the four React
 * sites:
 *
 *     scroll containers   Sports 6    PL 14    (20 in total)
 *     scrollbar rules     Sports 0    PL 0
 *     text inputs         Sports 2    PL 7     (so a caret exists to theme)
 *     native <select>     Sports 1    PL 4
 *     checkbox / radio    Sports 0    PL 0     <-- so accent-color would be DEAD CSS
 *
 * `accent-color` is in the backlog note and is deliberately **not** here. It
 * themes checkbox, radio and range, and the family has none of the three. Adding
 * it would have been a rule that looks like craft and can never fire — the
 * browser-default problem restated with extra steps. `color-scheme: dark` on the
 * root already handles the one native control the family does use, `<select>`.
 *
 * The scrollbar thumb is asserted by **contrast ratio, not by name**. The
 * tempting token is `--color-pr-rule`, and it measures 1.53:1 against the stage —
 * below the 3:1 WCAG 1.4.11 bar for a non-text UI part, which would have shipped
 * a scrollbar you cannot see. The token in use measures 6.83:1. Pinning the
 * *number* rather than the name means a future token change fails here instead of
 * quietly making the scrollbar invisible.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { contrast } from "./contrast";

const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8");
/** The same file with its comments removed: a comment is not configuration. */
const src = css.replace(/\/\*[\s\S]*?\*\//g, "");
const theme = /@theme\s*\{([^}]*)\}/.exec(src)?.[1] ?? "";
const token = (name: string) =>
  new RegExp(`--color-pr-${name}:\\s*(#[0-9a-fA-F]{6})`).exec(theme)?.[1] ?? "";

/** The declaration body of a rule whose SELECTOR is exactly `selector`. */
function decl(selector: string): string {
  const at = src.indexOf(selector);
  if (at < 0) return "";
  // Guard against matching the selector as a substring of a longer one: asked for
  // `::-webkit-scrollbar` it must not hand back the `::-webkit-scrollbar-thumb`
  // body that starts eleven characters later.
  const after = src[at + selector.length];
  if (after && !/[\s{]/.test(after)) return "";
  const open = src.indexOf("{", at);
  const close = src.indexOf("}", open);
  return src.slice(open + 1, close);
}

/** The body of the `[data-sport]` rule inside `@layer base`. */
function baseBlock(): string {
  const layer = /@layer base\s*\{([\s\S]*?)\n\}/.exec(src)?.[1] ?? "";
  const at = layer.indexOf("[data-sport]");
  if (at < 0) return "";
  return layer.slice(layer.indexOf("{", at) + 1, layer.indexOf("}", at));
}

/** The body of EVERY `[data-sport] … { }` rule in the file.
 *
 *  Every one, not the first. The first version of the document-scope guard read
 *  only the first, so moving the scrollbar under a *second* `[data-sport]` block
 *  sailed past it — the mutation the guard exists to catch was the one mutation
 *  it did not catch.
 */
function sportBlocks(): string[] {
  // `[data-sport] … {` only: a descendant rule like `[data-sport] ::-webkit-scrollbar {`
  // has more than whitespace between the `]` and the brace, so it is correctly
  // not counted as a sport block.
  return [...src.matchAll(/\[data-sport[^\]]*\]\s*\{([^}]*)\}/g)].map((m) => m[1]);
}

/** The full selector of every webkit scrollbar rule. */
function webkitSelectors(): string[] {
  return [...src.matchAll(/([^{};]*::-webkit-scrollbar[\w-]*)\s*\{/g)].map((m) => m[1].trim());
}

describe("browser surfaces", () => {
  it("themes the caret, because the family has text inputs to type into", () => {
    // Asserted on the rule that HOLDS the declaration, not on the text after the
    // property name. The first version searched for "caret-color" and read
    // forward to the next brace, which is the next RULE, so it would have failed
    // on a correct fix as surely as it failed on a missing one.
    expect(baseBlock(), "no [data-sport] rule in the base layer").toMatch(
      /caret-color:\s*var\(--color-pr-accent\)/,
    );
  });

  it("gives the caret a colour every sport can be seen against", () => {
    // Six accents, six answers. A caret that vanishes on one sport's page is a
    // bug no component screenshot can show.
    //
    // This one passed before the change and still passes after it, because it
    // guards the PALETTE rather than the rule — it fails the day someone points
    // the caret at a subtler token, not the day the caret is added.
    const stage = token("stage");
    // The message goes on `expect`, not on `toMatch` — vitest's `toMatch` takes
    // exactly one argument, and `vitest run` will not tell you so because esbuild
    // strips the types without checking them. `tsc --noEmit` did.
    expect(stage, "could not read the stage token").toMatch(/^#/);
    for (const sport of ["pl", "f1", "nfl", "cfb", "nba", "hub"]) {
      const scope = new RegExp(`\\[data-sport="${sport}"\\]\\s*\\{([^}]*)\\}`).exec(src)?.[1] ?? "";
      const accent = /--color-pr-accent:\s*(#[0-9a-fA-F]{6})/.exec(scope)?.[1] ?? token("accent");
      expect(accent, `no accent resolved for ${sport}`).toMatch(/^#/);
      expect(contrast(accent, stage), `${sport} caret on the stage`).toBeGreaterThanOrEqual(3);
    }
  });

  it("themes the scrollbar thumb from a token, not a literal", () => {
    // A hex here would bypass tokens.test.ts entirely: that guard reads the
    // @theme block, so a colour written straight into a rule is invisible to it.
    const block = decl("::-webkit-scrollbar-thumb");
    expect(block, "no webkit scrollbar thumb rule").not.toBe("");
    expect(block).toMatch(/var\(--color-pr-[\w-]+\)/);
    expect(block, "a literal colour in the scrollbar bypasses the contrast guard")
      .not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it("keeps the scrollbar thumb visible enough to grab", () => {
    // WCAG 1.4.11 asks 3:1 of a non-text UI part against its backdrop. The
    // scrollbar sits on the stage, so that is the pair to measure. Asserting the
    // number rather than the token name is the point: a token can be changed to a
    // nicer, subtler value later, and this fails then.
    const block = decl("::-webkit-scrollbar-thumb");
    const name = /var\(--color-pr-([\w-]+)\)/.exec(block)?.[1];
    expect(name, "the thumb must come from a family token").toBeTruthy();
    const thumb = token(name!);
    expect(thumb, `could not resolve --color-pr-${name}`).toMatch(/^#/);
    expect(contrast(thumb, token("stage")), `--color-pr-${name} on the stage`)
      .toBeGreaterThanOrEqual(3);
  });

  it("recedes the track so the thumb is the only visible part", () => {
    // A track painted lighter than the stage is a second stripe competing with
    // the content, on a page that is mostly lists.
    const track = decl("::-webkit-scrollbar-track");
    expect(track).toMatch(/background[^;]*var\(--color-pr-stage\)/);
  });

  it("themes the scrollbar at the DOCUMENT level, not under the sport", () => {
    // The one finding a source test alone would have shipped wrong, and a
    // browser found: `AppFrame` renders `<div data-sport={sport}>`, so in all
    // five sites the sport subtree is a DIV and the scrolling element is the
    // document, which is outside it. `scrollbar-color` and `scrollbar-width` do
    // not inherit, and `::-webkit-scrollbar` under `[data-sport]` only reaches
    // descendants — so scoping them to the sport themes a scrollbar nobody sees
    // and leaves the real one on the system default.
    //
    // Measured in a real browser before this was understood: the harness carries
    // `data-sport` on a `<main>`, the document overflowed 2902px in a 700px
    // viewport, and `getComputedStyle(document.documentElement).scrollbarColor`
    // was `auto` while the same property on the sport element read
    // `rgb(144, 154, 168) rgb(11, 13, 16)` — the theme, applied one element too
    // deep to matter.
    //
    // So the scrollbar rules must sit at document scope. The caret stays under
    // the sport, because `caret-color` inherits into the subtree and the accent
    // genuinely differs per sport.
    // Two ways to get this wrong, so both are checked. Scoping the standard
    // properties under the sport themes the div; scoping the pseudo-elements
    // under the sport themes every scroller inside the div and still not the
    // document.
    const offending = sportBlocks().filter((b) => /scrollbar-color|scrollbar-width/.test(b));
    expect(offending, "a scrollbar declaration sits inside a [data-sport] block, so the document scrollbar keeps the browser default")
      .toEqual([]);

    const scoped = webkitSelectors().filter((s) => s.includes("data-sport"));
    expect(scoped, "a ::-webkit-scrollbar rule is scoped under the sport, so the document's own scrollbar is untouched")
      .toEqual([]);

    // And the theme must actually be there at document scope, or the two checks
    // above would also be satisfied by deleting the rules altogether.
    const root = /:root\s*\{([^}]*)\}/.exec(src)?.[1] ?? "";
    expect(root, "no :root block carrying the scrollbar theme").toMatch(/scrollbar-color:/);
    expect(webkitSelectors().length, "no ::-webkit-scrollbar rules at all").toBeGreaterThan(2);

    // The caret stays under the sport, because `caret-color` inherits into the
    // subtree and the accent genuinely differs per sport.
    expect(baseBlock(), "the caret must stay with the sport").toMatch(/caret-color:/);
  });

  it("uses the standard properties as well as the webkit ones", () => {
    // `scrollbar-color` and `scrollbar-width` are what Firefox and Chrome 121+
    // use. The ::-webkit-scrollbar block is not redundant: Safari implements the
    // pseudo-elements and not the standard pair, and Safari is where these sites
    // are read. Shipping only the standard pair leaves the iPhone scrollbar at
    // the system default, which is the exact thing being fixed.
    expect(src).toMatch(/scrollbar-color:/);
    expect(src).toMatch(/scrollbar-width:\s*thin/);
    expect(src).toMatch(/::-webkit-scrollbar\b/);
  });

  it("keeps every surface rule inside the base layer", () => {
    // Outside @layer base these would outrank utility classes, so a component
    // could not restyle a caret or a scrollbar it draws itself.
    const layer = /@layer base\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
    expect(layer, "no @layer base block found").toMatch(/caret-color:/);
    expect(layer).toMatch(/scrollbar-color:/);
  });

  it("does not restate the surfaces that were already right", () => {
    // ::selection, :focus-visible and tabular-nums shipped earlier. They are
    // pinned here so a future tidy-up cannot "consolidate" them and quietly drop
    // the [data-sport] scoping that makes them follow the sport accent.
    expect(src).toMatch(/\[data-sport\]\s*::selection/);
    expect(src).toMatch(/\[data-sport\]\s*:focus-visible/);
    expect(src).toMatch(/font-variant-numeric:\s*tabular-nums/);
  });
});
