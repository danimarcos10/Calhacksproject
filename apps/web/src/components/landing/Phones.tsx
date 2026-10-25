"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { Bar, ConfidenceRing, DecisionBar } from "@/components/Charts";
import { formatMs } from "@/lib/api";
import { ACTIONS, decisionCounts, share } from "@/lib/visual";
import { SAMPLE, SHOTS } from "./content";
import { Marks } from "./Marks";

export function LandingMark({ cue = 0 }: { cue?: number }) {
  return (
    <svg className="mark" data-mood={cue ? "nod" : "rest"} viewBox="0 0 28 16" aria-hidden="true">
      <rect x="0" y="6" width="28" height="4" rx="1" fill="currentColor" />
      <g key={cue}>
        <rect className="look-a" x="8" y="2" width="2" height="12" fill="currentColor" />
        <rect className="look-b" x="17" y="2" width="2" height="12" fill="currentColor" />
      </g>
    </svg>
  );
}

export function PhotoPhone() {
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setAt((index) => (index + 1) % SHOTS.length);
    }, 6400);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="phone phone-photo" data-ui="">
      {SHOTS.map((shot, index) => (
        <div key={shot.src} className={index === at ? "shot on" : "shot"}>
          <Image src={shot.src} width={600} height={960} alt={index === at ? shot.alt : ""} priority={index === 0} sizes="300px" />
          <Marks id={`phone-${index}`} width={600} height={960} shot={shot} chip={shot.label} drift={shot.drift} chipFloor={120} />
        </div>
      ))}
      <p className="phone-bar">
        <LandingMark />
        <span>Following {SHOTS[at].label}</span>
      </p>
    </div>
  );
}

export function SampleLanes() {
  const pct = (ms: number) => `${(ms / SAMPLE.durationMs) * 100}%`;
  return (
    <div className="lanes">
      <ul className="lane-labels">
        {ACTIONS.map((action) => <li key={action.id}>{action.lane}</li>)}
      </ul>
      <div className="lane-area">
        {ACTIONS.map((action) => (
          <div key={action.id} className="lane-track">
            {SAMPLE.moments.filter((moment) => moment.action === action.id).map((moment) => (
              <span key={moment.id} className={`tick ${moment.status}`} style={{ left: pct(moment.startMs) }} />
            ))}
          </div>
        ))}
        <span className="sweep"><span className="lane-playhead" /></span>
      </div>
      <span />
      <div className="lane-axis">
        <span>0:00</span>
        <span>0:15</span>
        <span>0:30</span>
      </div>
    </div>
  );
}

export function LanesPhone() {
  const rows = [SAMPLE.moments[0], SAMPLE.moments[1], SAMPLE.moments[3]];
  return (
    <div className="phone phone-data" data-ui="">
      <p className="phone-title">
        <strong>{SAMPLE.player}</strong>
        <span>{SAMPLE.clip} · 30 s · sample review</span>
      </p>
      <SampleLanes />
      <ul className="phone-rows">
        {rows.map((moment) => (
          <li key={moment.id} className={moment.status === "suggestion" ? "hover" : undefined}>
            <span className={`key ${moment.status === "suggestion" ? "outline" : "accepted"}`} />
            <span className="row-main">
              <strong>{sentence(moment.action)}</strong> <span className="num">{formatMs(moment.startMs)}</span>
              <span className="row-meta">{moment.outcomeDetail} · {moment.status === "suggestion" ? "AI suggestion" : "accepted"}</span>
            </span>
            {moment.status === "suggestion" && (
              <span className="row-actions">
                <span className="fake-btn">Accept</span>
                <span className="fake-btn">Reject</span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CardPhone() {
  return (
    <div className="phone phone-data" data-ui="">
      <p className="phone-title">
        <strong>Evidence confidence</strong>
        <span>{SAMPLE.player} · sample review</span>
      </p>
      <div className="confidence-head">
        <ConfidenceRing score={SAMPLE.confidence.score} band={SAMPLE.confidence.band} />
        <p>
          <strong>{SAMPLE.confidence.band}</strong>
          <span className="meta">Scored out of 100.</span>
        </p>
      </div>
      <ul className="confidence-parts">
        {SAMPLE.parts.map((part) => (
          <li key={part.label}>
            <span>{part.label}</span>
            <Bar value={share(part.points, part.max)} tone="ink" />
            <span className="num">{part.points} / {part.max}</span>
          </li>
        ))}
      </ul>
      <p className="phone-sub">Coach decisions</p>
      <DecisionBar counts={decisionCounts(SAMPLE.moments)} />
    </div>
  );
}

export function sentence(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
