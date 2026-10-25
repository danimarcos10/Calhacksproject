import { describe, expect, it } from "vitest";
import { currentRuns, decisionBlocked, momentStatus, silentRelabels } from "../../convex/lib/status";
import { buildSummary, type SummaryMoment, type SummaryWindow } from "../../convex/lib/summary";

describe("currentRuns", () => {
  const windows = [
    { id: "w1", currentRevision: 2 },
    { id: "w2", currentRevision: 1 },
  ];

  it("picks the newest run made for each window's current selection", () => {
    const runs = [
      { id: "r1", windowId: "w1", revisionNumber: 1, outdatedOnArrival: false, publishedAt: 10 },
      { id: "r2", windowId: "w1", revisionNumber: 2, outdatedOnArrival: false, publishedAt: 20 },
      { id: "r3", windowId: "w2", revisionNumber: 1, outdatedOnArrival: false, publishedAt: 5 },
    ];
    expect(Object.fromEntries(currentRuns(windows, runs))).toEqual({ w1: "r2", w2: "r3" });
  });

  it("never lets an older selection's late result replace the current one", () => {
    const runs = [
      { id: "new", windowId: "w1", revisionNumber: 2, outdatedOnArrival: false, publishedAt: 20 },
      { id: "late-old", windowId: "w1", revisionNumber: 1, outdatedOnArrival: true, publishedAt: 30 },
    ];
    expect(currentRuns(windows, runs).get("w1")).toBe("new");
  });

  it("leaves a corrected window without a current run until it is analysed again", () => {
    const runs = [{ id: "r1", windowId: "w1", revisionNumber: 1, outdatedOnArrival: false, publishedAt: 10 }];
    expect(currentRuns(windows, runs).has("w1")).toBe(false);
  });
});

describe("momentStatus and decisions", () => {
  it("derives every status from the run, the hold and the newest decision", () => {
    expect(momentStatus(false, false, "accept")).toBe("stale");
    expect(momentStatus(true, true, undefined)).toBe("held");
    expect(momentStatus(true, false, "accept")).toBe("accepted");
    expect(momentStatus(true, false, "reject")).toBe("rejected");
    expect(momentStatus(true, false, "reset")).toBe("suggestion");
    expect(momentStatus(true, false, undefined)).toBe("suggestion");
  });

  it("blocks any decision on stale evidence and accepting a held moment", () => {
    expect(decisionBlocked("stale", "accept")).toMatch(/older player selection/);
    expect(decisionBlocked("stale", "reject")).toMatch(/older player selection/);
    expect(decisionBlocked("held", "accept")).toMatch(/identity hold/);
    expect(decisionBlocked("held", "reject")).toBeNull();
    expect(decisionBlocked("suggestion", "accept")).toBeNull();
  });
});

describe("silentRelabels", () => {
  const box = { x: 0.5, y: 0.5, w: 0.05, h: 0.1 };

  it("flags an estimated box saved as manual without confirmation", () => {
    expect(silentRelabels([{ frameId: "f02", source: "estimated", box }], [{ frameId: "f02", source: "manual", box }])).toEqual(["f02"]);
  });

  it("accepts a confirmed estimate or a redrawn box", () => {
    expect(
      silentRelabels([{ frameId: "f02", source: "estimated", box }], [{ frameId: "f02", source: "manual", method: "confirmed_estimate", box }]),
    ).toEqual([]);
    expect(
      silentRelabels([{ frameId: "f02", source: "estimated", box }], [{ frameId: "f02", source: "manual", box: { ...box, x: 0.6 } }]),
    ).toEqual([]);
  });
});

describe("buildSummary", () => {
  const windows: SummaryWindow[] = [
    { order: 1, startMs: 0, endMs: 7_000, videoKey: "vid_a", prepared: true, analysed: true, gaps: ["The ball is not followed to a clear end."], noObservationReason: null },
    { order: 2, startMs: 7_000, endMs: 14_000, videoKey: "vid_a", prepared: false, analysed: false, gaps: [], noObservationReason: null },
  ];
  const base = { videoKey: "vid_a", windowOrder: 1, seekMs: 0, outcome: "not_observable" };
  const moments: SummaryMoment[] = [
    { ...base, id: "pass", category: "passing_action", startMs: 0, endMs: 1_084, visibleAction: "Strikes the ball", status: "accepted" },
    { ...base, id: "run", category: "off_ball_movement", startMs: 3_000, endMs: 5_000, visibleAction: "Runs to the box", status: "suggestion" },
    { ...base, id: "old", category: "first_touch", startMs: 500, endMs: 900, visibleAction: "Old", status: "stale" },
    { ...base, id: "no", category: "defending_action", startMs: 6_000, endMs: 6_500, visibleAction: "No", status: "rejected" },
  ];

  it("lists accepted moments by category and keeps stale and rejected ones out", () => {
    const summary = buildSummary(moments, windows);
    expect(summary.accepted).toEqual([expect.objectContaining({ category: "passing_action", moments: [expect.objectContaining({ id: "pass" })] })]);
    expect(summary.pending.map((m) => m.id)).toEqual(["run"]);
  });

  it("states what the footage does not establish without judging the player", () => {
    const lines = buildSummary(moments, windows).notEstablished;
    expect(lines).toContain("Window 1 (0.0 s–7.0 s): The ball is not followed to a clear end.");
    expect(lines).toContain("Window 2 (7.0 s–14.0 s) has no player selection yet, so it was not analysed.");
    expect(lines.join(" ")).not.toMatch(/weak|poor|bad|lacks/i);
  });

  it("reports coverage from exact intervals, merging overlaps", () => {
    const summary = buildSummary(moments, [...windows, { ...windows[0], order: 3, startMs: 5_000, endMs: 9_000 }]);
    expect(summary.analysedMs).toBe(9_000);
    expect(summary.shortlistMs).toBe(1_084 + 2_000);
  });

  it("is deterministic", () => {
    expect(buildSummary(moments, windows)).toEqual(buildSummary(moments, windows));
  });
});
