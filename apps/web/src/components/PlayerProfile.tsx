"use client";

import type { FunctionReturnType } from "convex/server";
import { api } from "../../convex/_generated/api";
import { AbilityShape, Bar, ConfidenceRing } from "@/components/Charts";
import { share } from "@/lib/visual";

type Review = FunctionReturnType<typeof api.review.get>;
type AbilityName = "ball_security" | "passing" | "carrying" | "involvement";

const ABILITY: Record<AbilityName, string> = {
  ball_security: "Ball security",
  passing: "Passing",
  carrying: "Carrying",
  involvement: "Involvement",
};

export function PlayerProfile({ review, onPlay }: { review: Review; onPlay: (eventIds: string[]) => void }) {
  const { profile } = review;
  const running = review.windows.some((item) => {
    const status = item.requests[0]?.status;
    return !status || status === "queued" || status === "running";
  });
  if (!profile) return running ? <p className="meta">The description is written when every clip finishes.</p> : null;
  return (
    <section className="player-profile">
      {profile?.summary ? <p className="finding">{profile.summary}</p> : <p className="meta">{running ? "The description is written when every clip finishes." : "No description yet."}</p>}
      {profile?.qualities.map((quality) => (
        <div key={quality.eventIds.join("-")}>
          <p className="finding">{quality.text}</p>
          <button type="button" className="link" onClick={() => onPlay(quality.eventIds)}>Play these moments</button>
        </div>
      ))}
      {profile?.ability.state === "withheld" && <p className="meta">{profile.ability.reason}</p>}
      {profile && profile.gaps.length > 0 && <p className="meta">Not seen: {profile.gaps.join(" ")}</p>}
    </section>
  );
}

export function ConfidenceCell({ review }: { review: Review }) {
  const { confidence } = review;
  return (
    <div className="confidence">
      <div className="confidence-head">
        <ConfidenceRing score={confidence.score} band={confidence.band} />
        <p>
          <strong>{confidence.band}</strong>
          <span className="meta">Scored out of 100 from the checkable footage behind this profile.</span>
        </p>
      </div>
      <ul className="confidence-parts">
        {confidence.parts.map((part) => (
          <li key={part.id}>
            <span>{part.label}</span>
            <Bar value={share(part.points, part.max)} tone="ink" />
            <span className="num">{part.points} / {part.max}</span>
          </li>
        ))}
      </ul>
      <details>
        <summary>How it is scored</summary>
        <ul className="confidence-detail">
          {confidence.parts.map((part) => (
            <li key={part.id}><strong>{part.label}</strong> <span className="meta">{part.detail}</span></li>
          ))}
        </ul>
      </details>
    </div>
  );
}

export function AbilityCell({ review }: { review: Review }) {
  const ability = review.profile?.ability;
  if (ability?.state !== "shown") return null;
  return (
    <div className="ability-cell">
      <AbilityShape dimensions={ability.dimensions.map((dimension) => ({ label: ABILITY[dimension.name], score: dimension.score }))} />
      <p className="meta">AI estimate, unverified. Overall <strong className="num">{ability.overall}</strong>.</p>
      <details>
        <summary>Reasons</summary>
        <ul className="ability-reasons">
          {ability.dimensions.map((dimension) => (
            <li key={dimension.name}>
              <strong>{ABILITY[dimension.name]}</strong> <span className="meta">{dimension.reason}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
