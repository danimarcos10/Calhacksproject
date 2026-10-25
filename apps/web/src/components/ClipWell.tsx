"use client";

import { useLookState } from "@/components/Look";

export function ClipWell({ ink = "#ffffff", at }: { ink?: string; at?: number }) {
  const { working, cue } = useLookState();
  const placed = at != null && Number.isFinite(at);
  const ratio = placed ? Math.min(1, Math.max(0, at)) : null;
  const mood = placed ? "place" : working > 0 ? "scan" : cue?.kind ?? "rest";
  return (
    <svg
      className="clip-well"
      data-mood={mood}
      viewBox="0 0 640 360"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      style={ratio == null ? undefined : { ["--at" as string]: String(ratio) }}
    >
      <rect className="look-line" x="40" y="176" width="560" height="8" fill="#1d5fbf" />
      <g key={cue?.key ?? 0}>
        <rect className="look-a" x="168" y="152" width="4" height="56" fill="#1d5fbf" />
        <rect className="look-b" x="412" y="152" width="4" height="56" fill={ink} />
      </g>
    </svg>
  );
}
