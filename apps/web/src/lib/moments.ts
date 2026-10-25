import { mergeIntervals } from "../../convex/lib/intervals";
import type { MomentStatus } from "../../convex/lib/status";

// Playback adds context around each evidence interval. The stored and displayed
// timestamps stay exact; only the playlist segment is padded.
export const CONTEXT_PAD_MS = 1500;

export type PlaylistMode = "current" | "accepted";

export interface PlayableMoment {
  id: string;
  videoKey: string;
  startMs: number;
  endMs: number;
  status: MomentStatus;
}

export interface Segment {
  videoKey: string;
  startMs: number;
  endMs: number;
  moments: { id: string; startMs: number; endMs: number }[];
}

const INCLUDED: Record<PlaylistMode, MomentStatus[]> = {
  current: ["suggestion", "held", "accepted"],
  accepted: ["accepted"],
};

export function buildPlaylist(
  moments: PlayableMoment[],
  mode: PlaylistMode,
  durations: Record<string, number>,
  padMs = CONTEXT_PAD_MS,
): Segment[] {
  const order: string[] = [];
  const byVideo = new Map<string, { startMs: number; endMs: number; moment: PlayableMoment }[]>();
  for (const moment of moments) {
    if (!INCLUDED[mode].includes(moment.status)) continue;
    if (!byVideo.has(moment.videoKey)) {
      byVideo.set(moment.videoKey, []);
      order.push(moment.videoKey);
    }
    const limit = durations[moment.videoKey] ?? Number.POSITIVE_INFINITY;
    byVideo.get(moment.videoKey)!.push({
      startMs: Math.max(0, moment.startMs - padMs),
      endMs: Math.min(limit, moment.endMs + padMs),
      moment,
    });
  }
  return order.flatMap((videoKey) =>
    mergeIntervals(byVideo.get(videoKey)!).map((merged) => ({
      videoKey,
      startMs: merged.startMs,
      endMs: merged.endMs,
      moments: merged.members
        .map(({ moment }) => ({ id: moment.id, startMs: moment.startMs, endMs: moment.endMs }))
        .sort((a, b) => a.startMs - b.startMs),
    })),
  );
}

export function playlistMs(segments: Segment[]): number {
  return segments.reduce((sum, segment) => sum + (segment.endMs - segment.startMs), 0);
}

export function playlistCount(segments: Segment[]): string {
  const moments = segments.reduce((sum, segment) => sum + segment.moments.length, 0);
  if (moments === segments.length) return String(moments);
  return `${moments} in ${segments.length} ${segments.length === 1 ? "segment" : "segments"}`;
}

export const STATUS_LABEL: Record<MomentStatus, string> = {
  suggestion: "AI suggestion",
  accepted: "Accepted",
  rejected: "Rejected",
  held: "Identity hold",
  stale: "Stale",
};
