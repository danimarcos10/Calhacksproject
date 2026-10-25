export type ActionId = "receive" | "pass" | "carry" | "loss";

type MomentLike = { action: string | null; outcome: string; outcomeDetail: string | null; status: string };
type FrameLike = { t: number; players: { id: number }[] };

export const ACTIONS: { id: ActionId; label: string; lane: string; good: string[]; goodLabel: string }[] = [
  { id: "receive", label: "Receives", lane: "Receive", good: ["controlled"], goodLabel: "controlled" },
  { id: "pass", label: "Passes", lane: "Pass", good: ["completed", "completed_visible"], goodLabel: "completed" },
  { id: "carry", label: "Carries", lane: "Carry", good: ["retained"], goodLabel: "retained" },
  { id: "loss", label: "Losses", lane: "Loss", good: [], goodLabel: "" },
];

const LIVE = new Set(["suggestion", "accepted", "held"]);

export function outcomeSplit(moments: MomentLike[]) {
  const live = moments.filter((moment) => LIVE.has(moment.status));
  return ACTIONS.map((action) => {
    const of = live.filter((moment) => moment.action === action.id);
    const good = of.filter(
      (moment) => action.good.includes(moment.outcomeDetail ?? moment.outcome) || action.good.includes(moment.outcome),
    ).length;
    return { id: action.id, label: action.label, goodLabel: action.goodLabel, total: of.length, good };
  });
}

export function decisionCounts(moments: { status: string }[]) {
  const count = (status: string) => moments.filter((moment) => moment.status === status).length;
  const accepted = count("accepted");
  const rejected = count("rejected");
  const held = count("held");
  const waiting = count("suggestion");
  return { accepted, rejected, held, waiting, decided: accepted + rejected, total: accepted + rejected + held + waiting };
}

export function missingSpans(frames: FrameLike[], id: number | null, minMs = 400) {
  if (id === null || !frames.length) return [];
  const first = frames[0].t;
  const last = frames[frames.length - 1].t;
  const spans: { startMs: number; endMs: number }[] = [];
  let seen: number | null = null;
  for (const frame of frames) {
    if (!frame.players.some((player) => player.id === id)) continue;
    const from = seen ?? first;
    if (frame.t - from > minMs) spans.push({ startMs: from, endMs: frame.t });
    seen = frame.t;
  }
  if (seen === null) return [{ startMs: first, endMs: last }];
  if (last - seen > minMs) spans.push({ startMs: seen, endMs: last });
  return spans;
}

export function shapePoints(values: number[], radius: number, centre = radius) {
  return values.map((value, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / values.length;
    const r = (Math.max(0, Math.min(100, value)) / 100) * radius;
    return { x: centre + Math.cos(angle) * r, y: centre + Math.sin(angle) * r };
  });
}

export function share(part: number, whole: number) {
  return whole > 0 ? Math.max(0, Math.min(1, part / whole)) : 0;
}
