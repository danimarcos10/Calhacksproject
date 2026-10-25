"use client";

import { useEffect, useRef } from "react";
import { formatMs } from "@/lib/api";
import { ACTIONS, share, shapePoints, type ActionId, type decisionCounts, type outcomeSplit } from "@/lib/visual";

type Counts = ReturnType<typeof decisionCounts>;
type Split = ReturnType<typeof outcomeSplit>;
type LaneMoment = { id: string; action: string | null; startMs: number; status: string };

export function Bar({ value, tone = "data" }: { value: number; tone?: "data" | "ink" | "grey" }) {
  return (
    <span className={`bar ${tone}`} aria-hidden="true">
      <span style={{ transform: `scaleX(${Math.max(0, Math.min(1, value))})` }} />
    </span>
  );
}

export function OutcomeStrip({ split, trackedMs, footageMs }: { split: Split; trackedMs: number; footageMs: number }) {
  const actions = split.reduce((sum, item) => sum + item.total, 0);
  return (
    <dl className="strip">
      {split.map((item) => {
        const note = item.goodLabel ? `${item.good} ${item.goodLabel}` : `of ${actions} actions`;
        const value = item.goodLabel ? share(item.good, item.total) : share(item.total, actions);
        return (
          <div key={item.id} className={item.total ? undefined : "zero"}>
            <dt>{item.label}</dt>
            <dd>
              <strong className="num">{item.total}</strong>
              <span className="note">{note}</span>
              <Bar value={value} tone={item.goodLabel ? "data" : "grey"} />
            </dd>
          </div>
        );
      })}
      <div className={trackedMs ? undefined : "zero"}>
        <dt>Tracked</dt>
        <dd>
          <strong className="num">{trackedMs ? `${seconds(trackedMs)}s` : "0s"}</strong>
          <span className="note">of {seconds(footageMs)}s footage</span>
          <Bar value={share(trackedMs, footageMs)} tone="ink" />
        </dd>
      </div>
    </dl>
  );
}

export function DecisionBar({ counts, compact = false }: { counts: Counts; compact?: boolean }) {
  const parts = [
    { key: "accepted", value: counts.accepted, label: "accepted" },
    { key: "held", value: counts.held, label: "held" },
    { key: "rejected", value: counts.rejected, label: "rejected" },
    { key: "waiting", value: counts.waiting, label: "waiting" },
  ].filter((part) => part.value > 0 || part.key === "accepted" || part.key === "waiting");
  const label = parts.map((part) => `${part.value} ${part.label}`).join(", ");
  return (
    <div className={compact ? "decisions compact" : "decisions"}>
      <div className="decision-bar" role="img" aria-label={label}>
        {counts.total === 0 ? <span className="seg waiting" style={{ flexGrow: 1 }} /> : parts.map((part) => (
          part.value > 0 && <span key={part.key} className={`seg ${part.key}`} style={{ flexGrow: part.value }} />
        ))}
      </div>
      {!compact && (
        <>
          <p className="decisions-total">
            <strong className="num">{counts.decided}</strong> of {counts.total} decided
          </p>
          <ul className="decision-key">
            {parts.map((part) => (
              <li key={part.key}>
                <span className={`key ${part.key}`} aria-hidden="true" />
                <span className="num">{part.value}</span> {part.label}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function ConfidenceRing({ score, band }: { score: number; band: string }) {
  const radius = 26;
  const length = 2 * Math.PI * radius;
  return (
    <svg className="ring" viewBox="0 0 64 64" role="img" aria-label={`${score} out of 100, ${band} evidence confidence`}>
      <circle cx="32" cy="32" r={radius} fill="none" stroke="#e6e6e6" strokeWidth="5" />
      <circle
        cx="32"
        cy="32"
        r={radius}
        fill="none"
        stroke="#1d5fbf"
        strokeWidth="5"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - share(score, 100))}
        transform="rotate(-90 32 32)"
      />
      <text x="32" y="37" textAnchor="middle" className="ring-value">{score}</text>
    </svg>
  );
}

export function AbilityShape({ dimensions }: { dimensions: { label: string; score: number }[] }) {
  const radius = 56;
  const cx = 140;
  const cy = 86;
  const at = (values: number[]) => shapePoints(values, radius).map((point) => ({ x: point.x - radius + cx, y: point.y - radius + cy }));
  const poly = (points: { x: number; y: number }[]) => points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const shape = at(dimensions.map((dimension) => dimension.score));
  const rim = at(dimensions.map(() => 100));
  const anchor = (index: number) => {
    const point = rim[index];
    if (Math.abs(point.x - cx) < 1) return { x: point.x, y: point.y < cy ? point.y - 10 : point.y + 20, align: "middle" as const };
    return point.x > cx ? { x: point.x + 10, y: point.y + 4, align: "start" as const } : { x: point.x - 10, y: point.y + 4, align: "end" as const };
  };
  return (
    <svg className="ability" viewBox="0 0 280 176" role="img" aria-label={dimensions.map((dimension) => `${dimension.label} ${dimension.score}`).join(", ")}>
      {[25, 50, 75, 100].map((level) => (
        <polygon key={level} points={poly(at(dimensions.map(() => level)))} fill="none" stroke="#e6e6e6" strokeWidth="1" />
      ))}
      {rim.map((point, index) => (
        <line key={dimensions[index].label} x1={cx} y1={cy} x2={point.x} y2={point.y} stroke="#e6e6e6" strokeWidth="1" />
      ))}
      <polygon points={poly(shape)} fill="rgba(29, 95, 191, 0.15)" stroke="#1d5fbf" strokeWidth="1.5" strokeLinejoin="round" />
      {shape.map((point, index) => (
        <circle key={dimensions[index].label} cx={point.x} cy={point.y} r="2.5" fill="#1d5fbf" />
      ))}
      {dimensions.map((dimension, index) => {
        const place = anchor(index);
        return (
          <text key={dimension.label} x={place.x} y={place.y} textAnchor={place.align} className="ability-label">
            {dimension.label} <tspan className="ability-score">{dimension.score}</tspan>
          </text>
        );
      })}
    </svg>
  );
}

export function ActionLanes({
  moments,
  durationMs,
  missing,
  videoRef,
  onPlay,
}: {
  moments: LaneMoment[];
  durationMs: number;
  missing: { startMs: number; endMs: number }[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onPlay: (id: string) => void;
}) {
  const area = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLSpanElement>(null);
  const length = Math.max(durationMs, 1);
  const pct = (ms: number) => `${(Math.max(0, Math.min(ms, length)) / length) * 100}%`;

  useEffect(() => {
    let frame = 0;
    let last = -1;
    const tick = () => {
      frame = requestAnimationFrame(tick);
      const video = videoRef.current;
      const box = area.current;
      const line = head.current;
      if (!video || !box || !line) return;
      const x = share(video.currentTime * 1000, length) * box.clientWidth;
      if (Math.abs(x - last) < 0.25) return;
      last = x;
      line.style.transform = `translateX(${x.toFixed(2)}px)`;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [length, videoRef]);

  return (
    <div className="lanes" role="group" aria-label="Actions on this clip by time">
      <ul className="lane-labels" aria-hidden="true">
        {ACTIONS.map((action) => <li key={action.id}>{action.lane}</li>)}
      </ul>
      <div className="lane-area" ref={area}>
        {missing.map((span) => (
          <span key={span.startMs} className="lane-gap" style={{ left: pct(span.startMs), width: pct(span.endMs - span.startMs) }} />
        ))}
        {ACTIONS.map((action) => (
          <div key={action.id} className="lane-track">
            {moments.filter((moment) => moment.action === (action.id as ActionId)).map((moment) => (
              <button
                key={moment.id}
                type="button"
                className={`tick ${moment.status}`}
                style={{ left: pct(moment.startMs) }}
                aria-label={`${action.lane} at ${formatMs(moment.startMs)}, ${moment.status}`}
                onClick={() => onPlay(moment.id)}
              />
            ))}
          </div>
        ))}
        <span className="lane-playhead" ref={head} aria-hidden="true" />
      </div>
      <span aria-hidden="true" />
      <div className="lane-axis" aria-hidden="true">
        <span>0:00</span>
        <span>{formatMs(length / 2).replace(/\.\d+$/, "")}</span>
        <span>{formatMs(length).replace(/\.\d+$/, "")}</span>
      </div>
      <ul className="meta lane-note" aria-hidden="true">
        <li><span className="key accepted" /> Accepted</li>
        <li><span className="key outline" /> Awaiting review</li>
        <li><span className="key held" /> Held</li>
        {missing.length > 0 && <li><span className="key gap" /> Not in the track</li>}
      </ul>
    </div>
  );
}

function seconds(ms: number) {
  return (ms / 1000).toFixed(1).replace(/\.0$/, "");
}
