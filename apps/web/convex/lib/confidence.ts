// Evidence confidence. Computed from tracked time and reviewed events.
// It says how much checkable footage backs a profile. It is not an ability score.

export type ConfidenceBand = "Low" | "Medium" | "High";

export interface ConfidenceEvent {
  windowOrder: number;
  status: string;
  outcome: string;
  attributionHold: boolean;
}

export interface ConfidenceClip {
  order: number;
  trackedMs: number;
}

export interface ConfidencePart {
  id: "footage" | "volume" | "consistency" | "clarity" | "review";
  label: string;
  points: number;
  max: number;
  detail: string;
}

const LIVE = new Set(["suggestion", "accepted", "held"]);
const UNCLEAR = new Set(["unclear", "not_observable", "not_applicable"]);

export function confidenceBand(score: number): ConfidenceBand {
  if (score >= 70) return "High";
  if (score >= 40) return "Medium";
  return "Low";
}

function points(value: number): number {
  return Math.round(value * 10) / 10;
}

export function evidenceConfidence(
  clips: ConfidenceClip[],
  events: ConfidenceEvent[],
): { score: number; band: ConfidenceBand; parts: ConfidencePart[] } {
  const live = events.filter((event) => LIVE.has(event.status));
  const trackedSeconds = clips.reduce((sum, clip) => sum + Math.max(0, clip.trackedMs), 0) / 1000;
  const clipsWithEvents = new Set(live.map((event) => event.windowOrder)).size;
  const clear = live.filter((event) => !event.attributionHold && !UNCLEAR.has(event.outcome)).length;
  const accepted = live.filter((event) => event.status === "accepted").length;
  const footage = Math.min(1, trackedSeconds / 120) * 25;
  const volume = Math.min(1, live.length / 20) * 25;
  const consistency = Math.min(1, clipsWithEvents / 3) * 20;
  const clarity = live.length ? (clear / live.length) * 15 : 0;
  const review = live.length ? (accepted / live.length) * 15 : 0;
  const parts: ConfidencePart[] = [
    {
      id: "footage",
      label: "Footage",
      points: points(footage),
      max: 25,
      detail: `${trim(trackedSeconds)}s tracked of 120s`,
    },
    {
      id: "volume",
      label: "Actions seen",
      points: points(volume),
      max: 25,
      detail: `${live.length} of 20 actions`,
    },
    {
      id: "consistency",
      label: "Clips with actions",
      points: points(consistency),
      max: 20,
      detail: `${clipsWithEvents} of 3 clips`,
    },
    {
      id: "clarity",
      label: "Clear outcomes",
      points: points(clarity),
      max: 15,
      detail: live.length ? `${clear} of ${live.length} actions` : "No actions yet",
    },
    {
      id: "review",
      label: "Coach accepted",
      points: points(review),
      max: 15,
      detail: live.length ? `${accepted} of ${live.length} actions` : "No actions yet",
    },
  ];
  const score = Math.round(parts.reduce((sum, part) => sum + part.points, 0));
  return { score, band: confidenceBand(score), parts };
}

function trim(value: number): string {
  const text = value.toFixed(1);
  return text.endsWith(".0") ? text.slice(0, -2) : text;
}
