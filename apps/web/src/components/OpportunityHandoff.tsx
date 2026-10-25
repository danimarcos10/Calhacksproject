"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  findCoaches,
  getReachPlan,
  listPrograms,
  sendOutreach,
  type ClipStats,
  type CoachResult,
  type League,
  type Program,
  type ProgramList,
  type ReachPlan,
} from "@/lib/api";
import { useWorking } from "@/components/Look";

const LEAGUES: { id: League; label: string }[] = [
  { id: "mls_next", label: "MLS NEXT" },
  { id: "ecnl", label: "ECNL" },
  { id: "ecnl_rl", label: "ECNL Regional League" },
  { id: "npl", label: "NPL" },
  { id: "usys", label: "USYS National League" },
  { id: "high_school", label: "High school" },
  { id: "club", label: "Other club" },
];

const STATES = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
  "Delaware", "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
  "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
  "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
  "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
  "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
  "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin",
  "Wyoming",
];

const EMAIL = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;
const GROUPS: { id: Program["fit"]; title: string }[] = [
  { id: "fit", title: "Good fit, we email these" },
  { id: "possible", title: "Possible" },
  { id: "reach", title: "Reach, not emailed yet" },
];

export function OpportunityHandoff({
  reviewId,
  playerName,
  stats,
  profile = "",
}: {
  reviewId: string;
  playerName: string;
  stats: ClipStats;
  profile?: string;
}) {
  const [position, setPosition] = useState("Fullback");
  const [gradYear, setGradYear] = useState("2027");
  const [stateName, setStateName] = useState("California");
  const [league, setLeague] = useState<League>("ecnl");
  const [email, setEmail] = useState("");
  const [clipUrl, setClipUrl] = useState("");
  const [busy, setBusy] = useState("");
  useWorking(busy !== "");
  const [error, setError] = useState("");
  const [programs, setPrograms] = useState<ProgramList | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [coaches, setCoaches] = useState<CoachResult | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const [plans, setPlans] = useState<Record<string, ReachPlan>>({});
  const [openPlan, setOpenPlan] = useState("");
  const signature = JSON.stringify(stats) + profile;

  useEffect(() => {
    setCoaches(null);
    setSent({});
    setPlans({});
    setOpenPlan("");
  }, [signature]);

  function edit(update: () => void, resetPrograms = false) {
    update();
    setCoaches(null);
    setSent({});
    setPlans({});
    setOpenPlan("");
    setError("");
    if (resetPrograms) {
      setPrograms(null);
      setChecked([]);
    }
  }

  function toggle(school: string) {
    setChecked((current) => {
      if (current.includes(school)) return current.filter((item) => item !== school);
      if (current.length >= 5) return current;
      return [...current, school];
    });
    setCoaches(null);
    setSent({});
    setError("");
  }

  async function loadPrograms() {
    setBusy("programs");
    setError("");
    setPrograms(null);
    setChecked([]);
    setCoaches(null);
    setSent({});
    try {
      const found = await listPrograms(reviewId, { state: stateName, league });
      setPrograms(found);
      setPlans({});
      setOpenPlan("");
      setChecked(found.programs.filter((item) => item.fit === "fit").slice(0, 5).map((item) => item.school));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The program list could not be read. Try again.");
    } finally {
      setBusy("");
    }
  }

  async function loadCoaches() {
    const year = Number(gradYear);
    setBusy("coaches");
    setError("");
    setCoaches(null);
    setSent({});
    try {
      const found = await findCoaches(reviewId, {
        player_name: playerName,
        player_email: email.trim(),
        position: position.trim(),
        grad_year: year,
        state: stateName,
        league,
        clip_url: clipUrl.trim(),
        schools: checked.slice(0, 5),
        stats,
        profile,
      });
      setCoaches(found);
      setDrafts(Object.fromEntries(found.cards.map((card) => [card.school, card.draft])));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The coaches pages could not be read. Try again.");
    } finally {
      setBusy("");
    }
  }

  async function loadPlan(school: string) {
    if (plans[school]) {
      setOpenPlan((current) => (current === school ? "" : school));
      return;
    }
    const year = Number(gradYear);
    setBusy(`plan:${school}`);
    setError("");
    try {
      const plan = await getReachPlan(reviewId, {
        position: position.trim(),
        grad_year: year,
        state: stateName,
        league,
        school,
        stats,
        profile,
      });
      setPlans((current) => ({ ...current, [school]: plan }));
      setOpenPlan(school);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The plan could not be written. Try again.");
    } finally {
      setBusy("");
    }
  }

  async function send(school: string, address: string, subject: string) {
    if (!coaches) return;
    setBusy(school);
    setError("");
    try {
      const result = await sendOutreach(reviewId, {
        result_id: coaches.result_id,
        email: address,
        subject,
        body: drafts[school] ?? "",
        reply_to: email.trim(),
      });
      setSent((current) => ({ ...current, [school]: result.test_mode }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The email could not be sent. Try again.");
    } finally {
      setBusy("");
    }
  }

  const year = Number(gradYear);
  const yearOk = Number.isInteger(year) && year >= 2024 && year <= 2035;
  const emailOk = EMAIL.test(email.trim());
  const clipOk = !clipUrl.trim() || clipUrl.trim().startsWith("https://");
  const rows = preview(stats);
  const runs = coaches
    ? coaches.actors.map((actor, index) => `${actor} · ${coaches.run_ids[index] ?? ""}`.trim()).join("  ")
    : "";

  return (
    <section className="scout-next">
      <h2>Coaches to contact</h2>
      <p className="scout-status">Fit comes from the league you listed, not from this clip. It sorts schools. It does not predict a roster spot. Reach schools are not emailed. Replies go to you.</p>
      <table className="inventory scout-stats">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th>{label}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="scout-status">
        {stats.reviewed ? "Counted from accepted moments." : "Counted from suggestions. None are accepted yet."}
      </p>
      <div className="scout-facts">
        <label>
          Position
          <input value={position} onChange={(event) => edit(() => setPosition(event.target.value))} />
        </label>
        <label>
          Graduation year
          <input value={gradYear} inputMode="numeric" onChange={(event) => edit(() => setGradYear(event.target.value))} />
        </label>
        <label>
          State
          <select value={stateName} onChange={(event) => edit(() => setStateName(event.target.value), true)}>
            {STATES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          League
          <select value={league} onChange={(event) => edit(() => setLeague(event.target.value as League), true)}>
            {LEAGUES.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </label>
        <label>
          Your email
          <input value={email} inputMode="email" onChange={(event) => edit(() => setEmail(event.target.value))} />
        </label>
        <label>
          Clip link, optional
          <input value={clipUrl} onChange={(event) => edit(() => setClipUrl(event.target.value))} placeholder="https://" />
        </label>
      </div>
      <button type="button" className="primary" disabled={busy !== "" || !yearOk} onClick={() => void loadPrograms()}>
        {busy === "programs" ? "Reading program lists" : "Show programs"}
      </button>
      {busy === "programs" && <p className="scout-status">Reading program lists</p>}
      {programs && (
        <div>
          <p className="scout-status">{programs.rule} {programs.note}</p>
          {programs.message && <p className="scout-status">{programs.message}</p>}
          {GROUPS.map((group) => {
            const items = programs.programs.filter((program) => program.fit === group.id);
            if (items.length === 0) return null;
            return (
              <div key={group.id} className="scout-group">
                <h3>{group.title}</h3>
                <div className="scout-checks open">
                  {items.map((program) =>
                    group.id === "reach" ? (
                      <div key={program.school} className="scout-reach">
                        <p>
                          {program.school} · {program.city} · {program.division === "d1" ? "NCAA Division I" : "NCAA Division II"} · {program.conference}
                        </p>
                        <p className="scout-status">{program.fit_reason}</p>
                        <button
                          type="button"
                          disabled={busy !== "" || !yearOk || !position.trim()}
                          onClick={() => void loadPlan(program.school)}
                        >
                          {busy === `plan:${program.school}` ? "Writing a plan" : openPlan === program.school ? "Hide the plan" : "What would it take?"}
                        </button>
                        {openPlan === program.school && plans[program.school] && (
                          <ReachCard plan={plans[program.school]} />
                        )}
                      </div>
                    ) : (
                      <label key={program.school}>
                        <input
                          type="checkbox"
                          checked={checked.includes(program.school)}
                          disabled={!checked.includes(program.school) && checked.length >= 5}
                          onChange={() => toggle(program.school)}
                        />
                        <span>
                          {program.school} · {program.city} · {program.division === "d1" ? "NCAA Division I" : "NCAA Division II"} · {program.conference}
                        </span>
                      </label>
                    ),
                  )}
                </div>
              </div>
            );
          })}
          <button
            type="button"
            className="primary"
            disabled={busy !== "" || !yearOk || !position.trim() || !emailOk || !clipOk || checked.length === 0}
            onClick={() => void loadCoaches()}
          >
            {busy === "coaches" ? "Reading coaches pages" : "Find coaches"}
          </button>
          {busy === "coaches" && <p className="scout-status">Reading coaches pages</p>}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {coaches && (
        <div>
          <p className="scout-status">
            {coaches.cache_status === "cached" ? `Last live read ${coaches.retrieved_at}.` : "Read just now."}
            {runs ? ` ${runs}` : ""}
          </p>
          {coaches.message && <p className="scout-status">{coaches.message}</p>}
          {coaches.cards.map((card) => (
            <article key={card.school} className="scout-card">
              <h3>{card.school}</h3>
              <p className="scout-status">{card.division === "d1" ? "NCAA Division I" : "NCAA Division II"} · {card.conference}</p>
              <p className="scout-status">
                {card.coach_name ? `${card.coach_name}${card.title ? `, ${card.title}` : ""}` : "No coach name was printed on the page."}
              </p>
              <p className="scout-status">
                {card.email || card.phone || "The page does not state a public email."}
                {card.url && (
                  <>
                    {" · "}
                    <a href={card.url} target="_blank" rel="noreferrer">Coaches page</a>
                  </>
                )}
              </p>
              {card.email && (
                <>
                  <textarea
                    className="scout-draft-edit"
                    value={drafts[card.school] ?? card.draft}
                    onChange={(event) => setDrafts((current) => ({ ...current, [card.school]: event.target.value }))}
                  />
                  <div className="scout-actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={busy !== "" || sent[card.school] !== undefined || !(drafts[card.school] ?? card.draft).trim()}
                      onClick={() => void send(card.school, card.email!, card.subject)}
                    >
                      {sent[card.school] === undefined && (busy === card.school ? "Sending" : "Send")}
                      {sent[card.school] === true && "Sent to test inbox"}
                      {sent[card.school] === false && "Sent"}
                    </button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ReachCard({ plan }: { plan: ReachPlan }) {
  return (
    <article className="scout-card">
      <p className="scout-status">{plan.reason}</p>
      <p>{plan.read}</p>
      {plan.steps.map((step) => (
        <div key={step.title}>
          <h3>
            {step.title}
            <span className="cost-tag">{step.cost}</span>
          </h3>
          <p className="scout-status">{step.detail}</p>
        </div>
      ))}
      <p className="scout-status">
        {plan.source === "claude" ? "Written by Claude from your stats." : "Standard steps."}
      </p>
    </article>
  );
}

function preview(stats: ClipStats) {
  const actions = stats.receives + stats.passes_attempted + stats.carries + stats.losses;
  const perMinute = stats.tracked_s > 0 ? (actions / (stats.tracked_s / 60)).toFixed(1).replace(/\.0$/, "") : "0";
  const tracked = stats.tracked_s.toFixed(1).replace(/\.0$/, "");
  return [
    ["Seconds tracked", tracked],
    ["Receives", String(stats.receives)],
    ["Passes", `${stats.passes_completed} completed of ${stats.passes_attempted}`],
    ["Carries", String(stats.carries)],
    ["Ball losses", String(stats.losses)],
    ["Actions a tracked minute", perMinute],
    ["Clips analysed", String(stats.clips)],
    ["Evidence confidence", String(stats.confidence)],
  ];
}
