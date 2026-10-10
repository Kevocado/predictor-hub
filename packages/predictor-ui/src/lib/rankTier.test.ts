import { describe, expect, it } from "vitest";
import { rankTier } from "./rankTier";

describe("rankTier", () => {
  // n = 20: green 1-7, yellow 8-14, red 15-20 (third = ceil(20/3) = 7)
  it("n=20: rank 1 is good, rank 7 is good, rank 8 is mid, rank 14 is mid, rank 15 is bad, rank 20 is bad", () => {
    expect(rankTier(1, 20)).toBe("good");
    expect(rankTier(7, 20)).toBe("good");
    expect(rankTier(8, 20)).toBe("mid");
    expect(rankTier(14, 20)).toBe("mid");
    expect(rankTier(15, 20)).toBe("bad");
    expect(rankTier(20, 20)).toBe("bad");
  });

  // n = 30: green 1-10, yellow 11-20, red 21-30 (third = ceil(30/3) = 10)
  it("n=30: rank 1 is good, rank 10 is good, rank 11 is mid, rank 20 is mid, rank 21 is bad, rank 30 is bad", () => {
    expect(rankTier(1, 30)).toBe("good");
    expect(rankTier(10, 30)).toBe("good");
    expect(rankTier(11, 30)).toBe("mid");
    expect(rankTier(20, 30)).toBe("mid");
    expect(rankTier(21, 30)).toBe("bad");
    expect(rankTier(30, 30)).toBe("bad");
  });

  // n = 32: green 1-11, yellow 12-22, red 23-32 (third = ceil(32/3) = 11)
  it("n=32: rank 1 is good, rank 11 is good, rank 12 is mid, rank 22 is mid, rank 23 is bad, rank 32 is bad", () => {
    expect(rankTier(1, 32)).toBe("good");
    expect(rankTier(11, 32)).toBe("good");
    expect(rankTier(12, 32)).toBe("mid");
    expect(rankTier(22, 32)).toBe("mid");
    expect(rankTier(23, 32)).toBe("bad");
    expect(rankTier(32, 32)).toBe("bad");
  });

  // n = 2: third = ceil(2/3) = 1, good=1, mid=none (2*1=2), bad=2
  it("n=2: rank 1 is good, rank 2 is bad", () => {
    expect(rankTier(1, 2)).toBe("good");
    expect(rankTier(2, 2)).toBe("bad");
  });

  // n = 3: third = ceil(3/3) = 1, good=1, mid=2, bad=3
  it("n=3: rank 1 is good, rank 2 is mid, rank 3 is bad", () => {
    expect(rankTier(1, 3)).toBe("good");
    expect(rankTier(2, 3)).toBe("mid");
    expect(rankTier(3, 3)).toBe("bad");
  });

  // rank 1 is always good
  it("rank 1 is always good for any n >= 2", () => {
    for (let n = 2; n <= 50; n++) {
      expect(rankTier(1, n)).toBe("good");
    }
  });

  // rank n is always bad
  it("rank n is always bad for any n >= 2", () => {
    for (let n = 2; n <= 50; n++) {
      expect(rankTier(n, n)).toBe("bad");
    }
  });

  // edge case: n=1 is not valid (validation drops it), but let's make sure it doesn't crash
  it("n=1: rank 1 is good (though validation should drop this)", () => {
    expect(rankTier(1, 1)).toBe("good");
  });
});