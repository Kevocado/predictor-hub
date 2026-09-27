import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

// The craft floor calls browser surfaces "the cheapest signal that a page was
// built rather than assembled, and the one models skip most reliably". This
// page had focus rings and tabular numerals and nothing else: text selection,
// the caret, scrollbars and form-control accents were all still the browser's,
// on a near-black stage where the defaults were built for a white page.
//
// These are cheap and they are the difference between a page that was designed
// and a page that was assembled, so they are asserted rather than left to taste.
// Two different questions, so two helpers.
//
// `hasSelector` must END at the brace (optionally after a comma-separated
// group). An earlier single helper allowed `[^{]*` in between, which meant
// `::selection_disabled { ... }` satisfied a test asking for `::selection` —
// so the guard passed a rule that had been deliberately renamed out of the way,
// which is the one thing it exists to catch.
//
// `hasDeclaration` is for properties, which live INSIDE a block and so cannot be
// matched as selectors at all. Tightening the first helper exposed that: three
// tests were asking a selector question about `caret-color`.
const hasSelector = (selector) => {
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`${esc}\\s*(?:,[^{]*?)?\\s*\\{`, "i").test(html);
};

const hasDeclaration = (property) =>
  new RegExp(`(?:^|[;{\\s])${property}\\s*:`, "i").test(html);

test("text selection is themed, not the browser's blue", () => {
  assert.ok(hasSelector("::selection"), "no ::selection rule; selection is the browser default");
  // Assert on the BACKGROUND specifically, not "the rule mentions a token
  // somewhere". The rule also sets `color`, so a loose check passed an
  // off-palette background as long as the text colour was a token — which is
  // the exact substitution a future edit makes without noticing.
  const block = html.match(/::selection\s*\{([^}]*)\}/i)[1];
  const background = block.match(/background\s*:\s*([^;]+);/i);
  assert.ok(background, `::selection sets no background: ${block.trim()}`);
  assert.match(
    background[1],
    /var\(--color-pr-/,
    `the selection background is not from the palette: ${background[1].trim()}. A colour of ` +
      `its own here is how the family starts drifting.`,
  );
  // Selected text still has to be readable, so the pairing is the inverse one.
  assert.match(
    block,
    /color\s*:\s*var\(--color-pr-accent-ink\)|color\s*:\s*var\(--color-pr-stage\)/,
    "selected text must sit on the dark ink or the light accent, not on a mid tone",
  );
});

test("scrollbars are themed, not the platform's", () => {
  assert.ok(hasSelector("::-webkit-scrollbar") || hasDeclaration("scrollbar-color"),
    "no scrollbar rule; the page scrolls at 390px and the scrollbar is the platform's");
});

test("form controls take the accent, not the platform blue", () => {
  // There is no form on this page today. The rule is here so the day someone
  // adds one, the checkbox does not arrive in macOS blue on a near-black stage
  // and the floor does not have to be re-read to notice.
  assert.ok(hasDeclaration("accent-color"), "no accent-color; the first control added would be platform blue");
  assert.match(html, /accent-color:[^;]*var\(--color-pr-/, "accent-color is not from the palette");
});

test("the caret is themed", () => {
  assert.ok(hasDeclaration("caret-color"), "no caret-color; the caret would be the browser's on a dark page");
});

test("the tab key is visible on every interactive element", () => {
  // The focus ring the floor asks for, asserted rather than assumed: a page can
  // pass a contrast check and still be unusable by keyboard.
  assert.match(html, /:focus-visible[^{]*\{[^}]*(outline|box-shadow)[^}]*\}/,
    "no focus-visible ring; keyboard focus would be the browser default on a dark page");
});

test("tabular data lines up", () => {
  assert.match(html, /font-variant-numeric:\s*tabular-nums/,
    "figures in the cards should be tabular so columns align");
});
