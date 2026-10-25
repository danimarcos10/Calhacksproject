import { describe, expect, it } from "vitest";
import { decisionCounts, missingSpans, outcomeSplit, shapePoints, share } from "./visual";

const moment = (action: string, outcomeDetail: string, status = "suggestion") => ({ action, outcome: "not_observable", outcomeDetail, status });

describe("outcome split", () => {
  it("counts live moments per action and the share that kept the ball", () => {
    const split = outcomeSplit([
      moment("pass", "completed", "accepted"),
      moment("pass", "intercepted"),
      moment("pass", "completed", "rejected"),
      moment("receive", "controlled", "held"),
      moment("carry", "retained", "stale"),
      moment("loss", "lost"),
    ]);
    expect(split.find((item) => item.id === "pass")).toMatchObject({ total: 2, good: 1 });
    expect(split.find((item) => item.id === "receive")).toMatchObject({ total: 1, good: 1 });
    expect(split.find((item) => item.id === "carry")).toMatchObject({ total: 0, good: 0 });
    expect(split.find((item) => item.id === "loss")).toMatchObject({ total: 1, good: 0 });
  });

  it("reads a coach-category completed outcome as completed", () => {
    const [, pass] = outcomeSplit([{ action: "pass", outcome: "completed_visible", outcomeDetail: null, status: "accepted" }]);
    expect(pass).toMatchObject({ total: 1, good: 1 });
  });
});

describe("decision counts", () => {
  it("leaves stale moments out of the total", () => {
    const counts = decisionCounts([{ status: "accepted" }, { status: "rejected" }, { status: "suggestion" }, { status: "held" }, { status: "stale" }]);
    expect(counts).toEqual({ accepted: 1, rejected: 1, held: 1, waiting: 1, decided: 2, total: 4 });
  });
});

describe("missing spans", () => {
  const frames = [0, 100, 200, 300, 900, 1000, 1100, 1800].map((t) => ({ t, players: t === 900 || t === 1800 ? [] : [{ id: 7 }] }));

  it("marks gaps longer than the threshold between boxes of the chosen player", () => {
    expect(missingSpans(frames, 7)).toEqual([
      { startMs: 300, endMs: 1000 },
      { startMs: 1100, endMs: 1800 },
    ]);
  });

  it("covers the whole clip when the player never has a box", () => {
    expect(missingSpans(frames, 3)).toEqual([{ startMs: 0, endMs: 1800 }]);
  });

  it("draws nothing without a chosen player", () => {
    expect(missingSpans(frames, null)).toEqual([]);
  });
});

describe("shape points", () => {
  it("starts at the top and goes clockwise", () => {
    const [top, right, bottom, left] = shapePoints([100, 50, 100, 0], 40);
    expect(top.x).toBeCloseTo(40);
    expect(top.y).toBeCloseTo(0);
    expect(right.x).toBeCloseTo(60);
    expect(bottom.y).toBeCloseTo(80);
    expect(left.x).toBeCloseTo(40);
  });

  it("clamps scores to the 0 to 100 scale", () => {
    expect(shapePoints([140], 10)[0].y).toBeCloseTo(0);
    expect(share(3, 0)).toBe(0);
    expect(share(5, 4)).toBe(1);
  });
});
