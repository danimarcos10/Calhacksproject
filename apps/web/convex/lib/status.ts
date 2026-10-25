// Pure review-state rules shared by Convex functions and the tests.

export type MomentStatus = "suggestion" | "accepted" | "rejected" | "held" | "stale";
export type DecisionAction = "accept" | "reject" | "reset";

export interface RunLike {
  id: string;
  windowId: string;
  revisionNumber: number;
  outdatedOnArrival: boolean;
  publishedAt: number;
}

export interface WindowLike {
  id: string;
  currentRevision: number;
}

// A window's current run is the newest published run for its current player
// selection. Arrival order never promotes a run made for an older selection.
export function currentRuns(windows: WindowLike[], runs: RunLike[]): Map<string, string> {
  const revisionByWindow = new Map(windows.map((window) => [window.id, window.currentRevision]));
  const best = new Map<string, RunLike>();
  for (const run of runs) {
    if (run.outdatedOnArrival) continue;
    if (revisionByWindow.get(run.windowId) !== run.revisionNumber) continue;
    const seen = best.get(run.windowId);
    if (!seen || run.publishedAt > seen.publishedAt) best.set(run.windowId, run);
  }
  return new Map([...best].map(([windowId, run]) => [windowId, run.id]));
}

export function momentStatus(
  runIsCurrent: boolean,
  attributionHold: boolean,
  latest: DecisionAction | undefined,
): MomentStatus {
  if (!runIsCurrent) return "stale";
  if (attributionHold) return "held";
  if (latest === "accept") return "accepted";
  if (latest === "reject") return "rejected";
  return "suggestion";
}

export function decisionBlocked(status: MomentStatus, action: DecisionAction): string | null {
  if (status === "stale") {
    return "This moment belongs to an older player selection. It stays in history and cannot be changed.";
  }
  if (status === "held" && action === "accept") {
    return "This moment is on an identity hold. Correct the player selection, then analyse the window again.";
  }
  return null;
}

// An estimated box keeps its label unless the coach confirms it as manual.
export function silentRelabels(
  previous: { frameId: string; source?: string; box?: { x: number; y: number; w: number; h: number } }[],
  next: { frameId: string; source?: string; method?: string; box?: { x: number; y: number; w: number; h: number } }[],
): string[] {
  const before = new Map(previous.map((anchor) => [anchor.frameId, anchor]));
  const flagged: string[] = [];
  for (const anchor of next) {
    const prior = before.get(anchor.frameId);
    if (!prior || prior.source !== "estimated" || anchor.source !== "manual") continue;
    if (anchor.method === "confirmed_estimate") continue;
    const same =
      prior.box &&
      anchor.box &&
      prior.box.x === anchor.box.x &&
      prior.box.y === anchor.box.y &&
      prior.box.w === anchor.box.w &&
      prior.box.h === anchor.box.h;
    if (same) flagged.push(anchor.frameId);
  }
  return flagged;
}
