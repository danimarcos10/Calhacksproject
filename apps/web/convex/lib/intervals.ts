export interface Interval {
  startMs: number;
  endMs: number;
}

export interface Merged<T> extends Interval {
  members: T[];
}

// Sorts and merges intervals that overlap or touch. Members keep their own times.
export function mergeIntervals<T extends Interval>(items: T[]): Merged<T>[] {
  const sorted = [...items].sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const merged: Merged<T>[] = [];
  for (const item of sorted) {
    const last = merged[merged.length - 1];
    if (last && item.startMs <= last.endMs) {
      last.endMs = Math.max(last.endMs, item.endMs);
      last.members.push(item);
    } else {
      merged.push({ startMs: item.startMs, endMs: item.endMs, members: [item] });
    }
  }
  return merged;
}

export function totalMs(intervals: Interval[]): number {
  return intervals.reduce((sum, item) => sum + Math.max(0, item.endMs - item.startMs), 0);
}
