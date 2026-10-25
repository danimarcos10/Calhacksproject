import { describe, expect, it } from "vitest";
import { nextAttention, summarize, type FrameMark } from "./attention";

const frames = ["f01", "f02", "f03", "f04", "f05"];

function marks(partial: Record<string, FrameMark>): Record<string, FrameMark> {
  return Object.fromEntries(frames.map((id) => [id, partial[id] ?? { state: "unmarked" as const }]));
}

describe("frame attention", () => {
  it("counts each annotation state separately", () => {
    const counts = summarize([
      { state: "unmarked" },
      { state: "located", source: "manual" },
      { state: "located", source: "estimated" },
      { state: "not_visible" },
      { state: "uncertain" },
    ]);
    expect(counts).toEqual({ unmarked: 1, manual: 1, estimated: 1, notVisible: 1, uncertain: 1 });
  });

  it("jumps to an uncertain frame before an unmarked gap", () => {
    const draft = marks({
      f01: { state: "located", source: "manual" },
      f03: { state: "uncertain" },
      f05: { state: "located", source: "manual" },
    });
    expect(nextAttention(frames, draft)).toBe("f03");
  });

  it("jumps to an unannotated frame between locations", () => {
    const draft = marks({
      f01: { state: "located", source: "manual" },
      f05: { state: "located", source: "estimated" },
    });
    expect(nextAttention(frames, draft)).toBe("f02");
  });
});
