import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const tokens = readFileSync(new URL("../packages/predictor-ui/src/tokens.css", import.meta.url), "utf8");
const HOST = "40-160-91-131\\.sslip\\.io";

test("links point at the VPS sites, not the retired Azure apps", () => {
  assert.doesNotMatch(html, /azurecontainerapps\.io/);
  for (const sub of ["pl", "f1", "nba"]) assert.match(html, new RegExp(`href="https://${sub}\\.${HOST}"`));
  for (const sport of ["nfl", "cfb"]) assert.match(html, new RegExp(`href="https://sports\\.${HOST}/\\?sport=${sport}"`));
});

test("carries the family frame: wordmark and a switcher to every sport", () => {
  assert.match(html, /<body data-sport="hub">/);
  assert.match(html, /class="wordmark">Predictor</);
  const nav = html.match(/<nav aria-label="Sports"[\s\S]*?<\/nav>/);
  assert.ok(nav, "sport switcher nav");
  assert.deepEqual([...nav[0].matchAll(/>(\w+)<\/a>/g)].map((m) => m[1]), ["PL", "F1", "NFL", "CFB", "NBA"]);
});

test("one card per sport, each in its own accent", () => {
  const cards = [...html.matchAll(/<a class="sport pr-notch" data-sport="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(cards, ["pl", "f1", "nfl", "cfb", "nba"]);
});

test("inlined tokens match predictor-ui's tokens.css exactly", () => {
  const decls = (css) => Object.fromEntries([...css.matchAll(/(--(?:color|font|radius)-pr-[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  const base = decls(tokens.slice(0, tokens.indexOf("[data-sport=")));
  const mine = decls(html);
  for (const [name, value] of Object.entries(base)) assert.equal(mine[name], value, name);
  for (const sport of ["pl", "f1", "nfl", "cfb", "nba"]) {
    const accent = (css) => css.match(new RegExp(`\\[data-sport="${sport}"\\]\\s*\\{[^}]*--color-pr-accent:\\s*([^;]+);`))?.[1];
    assert.equal(accent(html), accent(tokens), `${sport} accent`);
  }
});

test("the family type and stage: no Inter, no glow, no emoji icons", () => {
  assert.match(html, /family=Barlow/);
  assert.doesNotMatch(html, /Inter/);
  assert.doesNotMatch(html, /radial-gradient/);
  assert.doesNotMatch(html, /\p{Extended_Pictographic}/u);
});

test("status is honest words, at least 12px", () => {
  assert.doesNotMatch(html, /Work in progress|walk-forward|no login required/i);
  const status = [...html.matchAll(/<span class="status">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(status, ["In season", "In season", "In season", "In season", "Preseason"]);
  const size = html.match(/\.status\s*\{[^}]*font-size:\s*([\d.]+)rem/);
  assert.ok(size && parseFloat(size[1]) >= 0.75, "status text is under 12px");
});

test("states the honesty rule once, plainly", () => {
  assert.match(html, /Only picks made before the game starts count/);
});

test("calls itself Sports Predictor in the title, the heading, and the share card", () => {
  // The page had three brand surfaces saying "Predictor" and no og:title at
  // all, so a shared link showed the bare family name with no description.
  assert.match(html, /<title>Sports Predictor<\/title>/);
  assert.match(html, /<h1[^>]*>Sports Predictor<\/h1>/);
  const og = html.match(/<meta property="og:title" content="([^"]+)"/);
  assert.ok(og, "no og:title, so a shared link has no title to show");
  assert.equal(og[1], "Sports Predictor");
  // og:description reuses the existing meta description rather than inventing
  // copy: two descriptions would drift, and only one of them would get updated.
  const desc = html.match(/<meta name="description" content="([^"]+)"/);
  const ogDesc = html.match(/<meta property="og:description" content="([^"]+)"/);
  assert.ok(ogDesc, "og:title without og:description is a half-done share card");
  assert.equal(ogDesc[1], desc[1]);
});

test("the wordmark stays the family name, not the product name", () => {
  // Deliberate, and pinned so it cannot drift by accident. The wordmark is the
  // shared frame every Predictor site carries in its header; the five sport
  // sites all say "Predictor" there. This page's own name is Sports Predictor,
  // but making its wordmark differ from the five would break the one thing the
  // wordmark is for -- telling a reader they are in the same family.
  const wordmark = html.match(/class="wordmark">([^<]+)</);
  assert.ok(wordmark, "no wordmark");
  assert.equal(wordmark[1], "Predictor");
});

test("every card has a picks teaser slot beneath it, not inside it", () => {
  // Kevin asked for the picks "underneath the cards". A teaser with its own
  // links cannot live inside the card's <a> -- nesting interactive content in
  // an anchor is invalid HTML -- so the slot is a sibling in the same <li>.
  const slots = [...html.matchAll(/<div class="teaser" data-teaser="(\w+)" aria-busy="true">/g)].map((m) => m[1]);
  assert.deepEqual(slots, ["pl", "f1", "nfl", "cfb", "nba"]);

  // And the slot must be a sibling of the card, not a descendant: an <a> that
  // still contains "teaser" means someone nested it later.
  for (const anchor of html.match(/<a class="sport pr-notch"[\s\S]*?<\/a>/g) || []) {
    assert.doesNotMatch(anchor, /class="teaser"/, "a teaser was nested inside the card's anchor");
  }
});

test("the cards themselves are untouched by the teasers", () => {
  const cards = [...html.matchAll(/<a class="sport pr-notch" data-sport="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(cards, ["pl", "f1", "nfl", "cfb", "nba"]);
  const status = [...html.matchAll(/<span class="status">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(status, ["In season", "In season", "In season", "In season", "Preseason"]);
});

test("the hub loads the teaser module", () => {
  assert.match(html, /<script type="module" src="\.\/teasers\.js"><\/script>/);
});

