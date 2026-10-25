import { describe, expect, it } from "vitest";
import { confidenceBand, evidenceConfidence, type ConfidenceEvent } from "../../convex/lib/confidence";

function event(partial: Partial<ConfidenceEvent> & Pick<ConfidenceEvent, "windowOrder">): ConfidenceEvent {
  return { status: "suggestion", outcome: "completed", attributionHold: false, ...partial };
}

describe("evidenceConfidence", () => {
  it("scores a short clip with a few clear actions as low", () => {
    const events = Array.from({ length: 7 }, () => event({ windowOrder: 1 }));
    const result = evidenceConfidence([{ order: 1, trackedMs: 29500 }], events);
    expect(result.parts.find((part) => part.id === "footage")?.points).toBe(6.1);
    expect(result.parts.find((part) => part.id === "volume")?.points).toBe(8.8);
    expect(result.parts.find((part) => part.id === "consistency")?.points).toBe(6.7);
    expect(result.parts.find((part) => part.id === "clarity")?.points).toBe(15);
    expect(result.parts.find((part) => part.id === "review")?.points).toBe(0);
    expect(result.score).toBe(37);
    expect(result.band).toBe("Low");
  });

  it("rises when the same actions show up across three clips", () => {
    const events = Array.from({ length: 20 }, (_, index) => event({ windowOrder: (index % 3) + 1 }));
    const result = evidenceConfidence(
      [
        { order: 1, trackedMs: 16000 },
        { order: 2, trackedMs: 16000 },
        { order: 3, trackedMs: 16000 },
      ],
      events,
    );
    expect(result.parts.find((part) => part.id === "consistency")?.points).toBe(20);
    expect(result.parts.find((part) => part.id === "volume")?.points).toBe(25);
    expect(result.score).toBe(70);
    expect(result.band).toBe("High");
  });

  it("ignores rejected and stale moments", () => {
    const result = evidenceConfidence([{ order: 1, trackedMs: 0 }], [
      event({ windowOrder: 1, status: "rejected" }),
      event({ windowOrder: 1, status: "stale" }),
      event({ windowOrder: 2, status: "accepted", outcome: "unclear" }),
    ]);
    expect(result.parts.find((part) => part.id === "volume")?.detail).toBe("1 of 20 actions");
    expect(result.parts.find((part) => part.id === "clarity")?.points).toBe(0);
    expect(result.parts.find((part) => part.id === "review")?.points).toBe(15);
    expect(result.parts.find((part) => part.id === "consistency")?.detail).toBe("1 of 3 clips");
  });

  it("does not treat an identity hold as a clear outcome", () => {
    const result = evidenceConfidence([{ order: 1, trackedMs: 0 }], [event({ windowOrder: 1, status: "held", attributionHold: true })]);
    expect(result.parts.find((part) => part.id === "clarity")?.points).toBe(0);
  });

  it("does not let a rejected moment on another clip raise the review points", () => {
    const acceptedOnly = evidenceConfidence(
      [
        { order: 1, trackedMs: 0 },
        { order: 2, trackedMs: 0 },
      ],
      [event({ windowOrder: 1, status: "accepted" })],
    );
    const withRejection = evidenceConfidence(
      [
        { order: 1, trackedMs: 0 },
        { order: 2, trackedMs: 0 },
      ],
      [event({ windowOrder: 1, status: "accepted" }), event({ windowOrder: 2, status: "rejected" })],
    );
    const acceptedPoints = acceptedOnly.parts.find((part) => part.id === "review")?.points;
    expect(withRejection.parts.find((part) => part.id === "review")?.points).toBe(acceptedPoints);
    expect(acceptedPoints).toBe(15);
    expect(withRejection.parts.find((part) => part.id === "volume")?.detail).toBe("1 of 20 actions");
  });

  it("bands the rounded score", () => {
    expect(confidenceBand(39)).toBe("Low");
    expect(confidenceBand(40)).toBe("Medium");
    expect(confidenceBand(69)).toBe("Medium");
    expect(confidenceBand(70)).toBe("High");
  });
});
