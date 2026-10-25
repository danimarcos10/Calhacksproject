// Deterministic review summary. No model call: every line comes from stored
// observations, decisions, window coverage and the model's own stated gaps.

import { mergeIntervals, totalMs } from "./intervals";
import type { MomentStatus } from "./status";

export const CATEGORY_LABELS: Record<string, string> = {
  first_touch: "First touch",
  passing_action: "Passing",
  carrying_action: "Carrying",
  defending_action: "Defending",
  off_ball_movement: "Off-ball movement",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, " ");
}

export interface SummaryMoment {
  id: string;
  category: string;
  videoKey: string;
  windowOrder: number;
  startMs: number;
  endMs: number;
  seekMs: number;
  visibleAction: string;
  outcome: string;
  status: MomentStatus;
}

export interface SummaryWindow {
  order: number;
  startMs: number;
  endMs: number;
  videoKey: string;
  prepared: boolean;
  analysed: boolean;
  gaps: string[];
  noObservationReason: string | null;
}

export interface Summary {
  accepted: { category: string; label: string; moments: SummaryMoment[] }[];
  pending: SummaryMoment[];
  notEstablished: string[];
  suggestedFootageRequest: string;
  analysedMs: number;
  shortlistMs: number;
}

const ACTIVE: MomentStatus[] = ["suggestion", "held", "accepted"];

export function buildSummary(moments: SummaryMoment[], windows: SummaryWindow[]): Summary {
  const accepted = new Map<string, SummaryMoment[]>();
  for (const moment of moments) {
    if (moment.status !== "accepted") continue;
    accepted.set(moment.category, [...(accepted.get(moment.category) ?? []), moment]);
  }
  const groups = Object.keys(CATEGORY_LABELS)
    .concat([...accepted.keys()].filter((key) => !(key in CATEGORY_LABELS)))
    .filter((key) => accepted.has(key))
    .map((key) => ({
      category: key,
      label: categoryLabel(key),
      moments: (accepted.get(key) ?? []).sort((a, b) => a.windowOrder - b.windowOrder || a.startMs - b.startMs),
    }));

  const pending = moments
    .filter((moment) => moment.status === "suggestion" || moment.status === "held")
    .sort((a, b) => a.windowOrder - b.windowOrder || a.startMs - b.startMs);

  const notEstablished: string[] = [];
  for (const window of [...windows].sort((a, b) => a.order - b.order)) {
    const label = `Window ${window.order} (${seconds(window.startMs)}–${seconds(window.endMs)})`;
    if (!window.prepared) {
      notEstablished.push(`${label} has no player selection yet, so it was not analysed.`);
    } else if (!window.analysed) {
      notEstablished.push(`${label} has no analysis for its current player selection yet.`);
    } else {
      if (window.noObservationReason) notEstablished.push(`${label}: ${window.noObservationReason}`);
      for (const gap of window.gaps) notEstablished.push(`${label}: ${gap}`);
    }
  }
  const missing = Object.keys(CATEGORY_LABELS).filter((key) => !accepted.has(key));
  if (missing.length) {
    notEstablished.push(
      `No accepted moment in the reviewed footage for: ${missing.map(categoryLabel).join(", ")}.`,
    );
  }

  const analysedMs = mergedByVideo(windows.filter((window) => window.analysed));
  const byVideo = new Map<string, SummaryMoment[]>();
  for (const moment of moments) {
    if (!ACTIVE.includes(moment.status)) continue;
    byVideo.set(moment.videoKey, [...(byVideo.get(moment.videoKey) ?? []), moment]);
  }
  const shortlistMs = mergedByVideo([...byVideo.values()].flat());

  const wanted = missing.length
    ? missing.map((key) => categoryLabel(key).toLowerCase()).join(", ")
    : "more of the same actions in different match situations";
  const suggestedFootageRequest =
    `Please send 30 to 90 seconds of uninterrupted match footage where the player stays in view, ` +
    `showing ${wanted}. A wide, steady camera angle and the shirt number visible at least once help most.`;

  return { accepted: groups, pending, notEstablished, suggestedFootageRequest, analysedMs, shortlistMs };
}

function mergedByVideo(items: { videoKey: string; startMs: number; endMs: number }[]): number {
  const groups = new Map<string, { startMs: number; endMs: number }[]>();
  for (const item of items) groups.set(item.videoKey, [...(groups.get(item.videoKey) ?? []), item]);
  return [...groups.values()].reduce((sum, list) => sum + totalMs(mergeIntervals(list)), 0);
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}
