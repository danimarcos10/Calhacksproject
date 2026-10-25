import { describe, expect, it } from "vitest";
import { buildScoutBrief, type BriefEvent } from "../../convex/lib/scoutBrief";

function event(partial: Partial<BriefEvent> & Pick<BriefEvent, "id" | "action">): BriefEvent {
  return { outcome: "completed", startMs: 0, visibleAction: "Plays the ball.", ...partial };
}

describe("buildScoutBrief", () => {
  it("states a repeated action as a pattern and a single one as an example", () => {
    const brief = buildScoutBrief([
      event({ id: "a", action: "pass", outcome: "completed" }),
      event({ id: "b", action: "pass", outcome: "intercepted", startMs: 4000 }),
      event({ id: "c", action: "pass", outcome: "unclear", startMs: 8000 }),
      event({ id: "d", action: "receive", outcome: "controlled", startMs: 1000, visibleAction: "Controls a pass into feet." }),
    ]);
    expect(brief.findings).toHaveLength(2);
    expect(brief.findings[0].text).toContain("3 passes");
    expect(brief.findings[0].text).toContain("1 intercepted");
    expect(brief.findings[0].text).toContain("outcome unclear");
    expect(brief.findings[0].eventIds).toEqual(["a", "b", "c"]);
    expect(brief.findings[1].text.startsWith("One example")).toBe(true);
    expect(brief.inventory.find((row) => row.action === "pass")?.unclear).toBe(1);
  });

  it("returns no finding when the events were removed", () => {
    expect(buildScoutBrief([]).findings).toEqual([]);
  });
});
