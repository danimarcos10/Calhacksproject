// Deterministic scouting brief. No model call. A finding exists only when an
// event supports it, and rejecting that event removes the finding on the next read.

export const ACTION_LABELS: Record<string, string> = {
  receive: "Receives",
  pass: "Passes",
  carry: "Carries",
  loss: "Losses",
};

const ORDER = ["pass", "receive", "carry", "loss"];

export interface BriefEvent {
  id: string;
  action: string;
  outcome: string;
  startMs: number;
  visibleAction: string;
}

export interface Finding {
  text: string;
  eventIds: string[];
}

export interface InventoryRow {
  action: string;
  label: string;
  known: { outcome: string; count: number }[];
  unclear: number;
}

const UNCLEAR = new Set(["unclear", "not_observable", "not_applicable"]);

export function buildScoutBrief(events: BriefEvent[]): { findings: Finding[]; inventory: InventoryRow[] } {
  const grouped = new Map<string, BriefEvent[]>();
  for (const event of events) {
    if (!(event.action in ACTION_LABELS)) continue;
    grouped.set(event.action, [...(grouped.get(event.action) ?? []), event]);
  }
  const findings = [...grouped.entries()]
    .sort((a, b) => b[1].length - a[1].length || ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
    .slice(0, 3)
    .map(([action, rows]) => ({
      text: findingText(action, rows),
      eventIds: rows.map((row) => row.id),
    }));
  const inventory = ORDER.filter((action) => grouped.has(action)).map((action) => inventoryRow(action, grouped.get(action) ?? []));
  return { findings, inventory };
}

function findingText(action: string, rows: BriefEvent[]): string {
  const label = ACTION_LABELS[action].toLowerCase();
  if (rows.length === 1) {
    const row = rows[0];
    return `One example in this footage: ${row.visibleAction} (${outcomePhrase(row.outcome)}).`;
  }
  const known = rows.filter((row) => !UNCLEAR.has(row.outcome));
  const unclear = rows.length - known.length;
  const tally = tallyText(known);
  const unclearText = unclear ? `${unclear} with the outcome unclear` : "";
  const detail = [tally, unclearText].filter(Boolean).join(", and ");
  return `In this footage, ${rows.length} ${label}${detail ? `: ${detail}` : ""}.`;
}

function tallyText(rows: BriefEvent[]): string {
  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.outcome, (counts.get(row.outcome) ?? 0) + 1);
  return [...counts.entries()].map(([outcome, count]) => `${count} ${outcomePhrase(outcome)}`).join(", ");
}

function outcomePhrase(outcome: string): string {
  const phrases: Record<string, string> = {
    completed: "completed",
    intercepted: "intercepted",
    out_of_play: "out of play",
    controlled: "controlled",
    miscontrolled: "miscontrolled",
    retained: "kept",
    lost: "lost",
    unclear: "outcome unclear",
    not_observable: "outcome unclear",
    completed_visible: "completed",
    unsuccessful_visible: "unsuccessful",
  };
  return phrases[outcome] ?? outcome.replace(/_/g, " ");
}

function inventoryRow(action: string, rows: BriefEvent[]): InventoryRow {
  const counts = new Map<string, number>();
  let unclear = 0;
  for (const row of rows) {
    if (UNCLEAR.has(row.outcome)) unclear += 1;
    else counts.set(row.outcome, (counts.get(row.outcome) ?? 0) + 1);
  }
  return {
    action,
    label: ACTION_LABELS[action],
    known: [...counts.entries()].map(([outcome, count]) => ({ outcome, count })),
    unclear,
  };
}
