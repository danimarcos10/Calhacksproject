"use client";

import { useMutation } from "convex/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../convex/_generated/api";
import type { Id } from "../../convex/_generated/dataModel";
import { API_ORIGIN, formatMs } from "@/lib/api";
import { OpportunityHandoff } from "@/components/OpportunityHandoff";
import { AbilityCell, ConfidenceCell, PlayerProfile } from "@/components/PlayerProfile";
import { ActionLanes, DecisionBar, OutcomeStrip } from "@/components/Charts";
import { decisionCounts, missingSpans, outcomeSplit } from "@/lib/visual";
import { VideoOverlay, trackAtClick, type TrackFrame } from "@/components/VideoOverlay";
import { buildPlaylist, playlistCount, type Segment } from "@/lib/moments";
import { errorText } from "@/lib/reviewAccess";
import { useCue, useWorking } from "@/components/Look";
import type { FunctionReturnType } from "convex/server";

type Review = FunctionReturnType<typeof api.review.get>;
type Moment = Review["moments"][number];
type Access = { key: string; code: string };

const FILTERS = [
  { id: "receive", label: "Receives" },
  { id: "pass", label: "Passes" },
  { id: "carry", label: "Carries" },
  { id: "loss", label: "Losses" },
  { id: "unsuccessful", label: "Unsuccessful" },
  { id: "unclear", label: "Outcome unclear" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"] | "all";

const UNSUCCESSFUL = new Set(["intercepted", "out_of_play", "miscontrolled", "lost", "unsuccessful_visible"]);

export function ScoutBoard({ review, access, reviewer }: { review: Review; access: Access; reviewer: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pendingSeek = useRef<Segment | null>(null);
  const [windowId, setWindowId] = useState(review.windows[0]?.id ?? "");
  const window = review.windows.find((item) => item.id === windowId) ?? review.windows[0];
  const [playing, setPlaying] = useState<{ index: number; segments: Segment[] } | null>(null);
  const [filter, setFilter] = useState<FilterId>("all");
  const [reviewedOnly, setReviewedOnly] = useState(false);
  const [message, setMessage] = useState("");
  const cancel = useMutation(api.review.cancelAnalysis);
  const saveRevision = useMutation(api.review.saveRevision);
  const queue = useMutation(api.review.queueAnalysis);
  const decide = useMutation(api.review.decide);
  const cue = useCue();
  const [framesByVideo, setFramesByVideo] = useState<Record<string, TrackFrame[]>>({});
  const request = window?.requests[0];
  const running = request?.status === "queued" || request?.status === "running";
  useWorking(Boolean(running));
  const seenStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    const status = request?.status;
    if (seenStatus.current && seenStatus.current !== "succeeded" && status === "succeeded") cue("meet");
    seenStatus.current = status;
  }, [request?.status, cue]);

  const durations = useMemo(
    () => Object.fromEntries(review.windows.map((item) => [item.videoKey, item.videoDurationMs])),
    [review.windows],
  );
  const visible = review.moments.filter((moment) => matches(moment, filter, reviewedOnly));
  const listed = visible.filter((moment) => moment.windowId === window?.id);
  const playlist = useMemo(
    () => buildPlaylist(visible, reviewedOnly ? "accepted" : "current", durations),
    [visible, reviewedOnly, durations],
  );

  async function acceptMoment(observationId: Id<"observations">) {
    await decide({ ...access, observationId, action: "accept", reviewer });
    cue("nod");
  }

  function play(segments: Segment[], index = 0) {
    const segment = segments[index];
    const player = videoRef.current;
    if (!segment || !player) return;
    const match = review.windows.find((item) => item.videoKey === segment.videoKey);
    setPlaying({ segments, index });
    if (match && match.videoKey !== window?.videoKey) {
      pendingSeek.current = segment;
      setWindowId(match.id);
      return;
    }
    player.currentTime = segment.startMs / 1000;
    void player.play();
  }

  const boundary = useRef<() => boolean>(() => false);
  useEffect(() => {
    boundary.current = () => {
      const player = videoRef.current;
      const segment = playing ? playing.segments[playing.index] : null;
      if (!playing || !player || !segment || segment.videoKey !== window?.videoKey || player.currentTime * 1000 < segment.endMs) return false;
      if (playing.index + 1 < playing.segments.length) play(playing.segments, playing.index + 1);
      else {
        player.pause();
        setPlaying(null);
      }
      return true;
    };
  });

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      if (!boundary.current()) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, window?.videoKey]);

  function playFinding(ids: string[]) {
    const wanted = new Set(ids);
    const chosen = review.moments.filter((moment) => wanted.has(moment.id) || wanted.has(moment.key));
    play(buildPlaylist(chosen, "current", durations));
  }

  async function correct(frameId: string, box: { x: number; y: number; w: number; h: number }) {
    if (!window?.revision) return;
    setMessage("");
    try {
      await saveRevision({
        ...access,
        windowId: window.id as Id<"windows">,
        baseRevision: window.currentRevision,
        anchors: [...window.revision.anchors, { frameId, state: "located", source: "manual", box }],
        jerseyNote: window.revision.jerseyNote,
        teamColorNote: window.revision.teamColorNote,
        note: window.revision.note,
        origin: "correction",
        reviewer,
      });
      await queue({ ...access, windowId: window.id as Id<"windows">, reviewer });
    } catch (error) {
      setMessage(errorText(error, "The correction could not be saved."));
    }
  }

  const duration = window?.videoDurationMs ?? 1;
  const correction = review.corrections.find((item) => item.windowId === window?.id);
  const frames = (window?.videoKey && framesByVideo[window.videoKey]) || [];

  const findings = narrativeFindings(review).slice(0, 3);
  const anchor = window?.revision?.anchors.find((item) => item.box);
  const clickMs = window?.frames.find((frame) => frame.frameId === anchor?.frameId)?.tMs ?? window?.startMs ?? 0;
  const selectedId = anchor?.box ? trackAtClick(frames, clickMs, anchor.box) : null;
  const clipMoments = review.moments.filter((moment) => moment.windowId === window?.id);
  const overlayMoments = clipMoments
    .filter((moment) => moment.status !== "rejected" && moment.status !== "stale")
    .map((moment) => ({ startMs: moment.startMs, endMs: moment.endMs, action: moment.action, outcome: moment.outcomeDetail }));
  const clipRun = review.runs.find((run) => run.current && run.windowOrder === window?.order);

  useEffect(() => {
    const videoKey = window?.videoKey;
    if (!videoKey) return;
    let stop = false;
    fetch(`${API_ORIGIN}/api/videos/${videoKey}/tracks`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!stop && body?.frames) {
          setFramesByVideo((current) => (current[videoKey] ? current : { ...current, [videoKey]: body.frames }));
        }
      })
      .catch(() => undefined);
    return () => {
      stop = true;
    };
  }, [window?.videoKey]);

  const tracked = trackedSeconds(review);
  const trackedLabel = tracked > 0 ? tracked.toFixed(1).replace(/\.0$/, "") : undefined;
  const footageMs = review.windows.reduce((sum, item) => sum + item.videoDurationMs, 0);
  const missing = missingSpans(frames, selectedId);
  const showAbility = review.profile?.ability.state === "shown";

  const lead = findings[0];

  return (
    <div>
      <header className="title-row board-head">
        <div>
          <h1>{review.submission.player}</h1>
          <PlayerProfile review={review} onPlay={playFinding} />
          {!review.profile && (lead ? <p className="finding">{lead.text}</p> : <p className="finding">No finding yet.</p>)}
          <p className="sub">AI-generated, awaiting review.</p>
          {!review.profile && lead && (
            <button type="button" className="primary" onClick={() => playFinding(lead.eventIds)}>Play these moments</button>
          )}
          {!review.profile && findings.slice(1).map((finding) => (
            <div key={finding.eventIds.join("-")}>
              <p className="finding">{finding.text}</p>
              <button type="button" className="link" onClick={() => playFinding(finding.eventIds)}>Play these moments</button>
            </div>
          ))}
        </div>
        <section className="panel board-card" aria-label="Evidence confidence">
          <h2>Evidence confidence</h2>
          <ConfidenceCell review={review} />
        </section>
      </header>
      <section className={showAbility ? "board-band three" : "board-band"} aria-label="Evidence at a glance">
        <div className="band-cell">
          <h2>What the clips show</h2>
          <OutcomeStrip split={outcomeSplit(review.moments)} trackedMs={tracked * 1000} footageMs={footageMs} />
        </div>
        <div className="band-cell">
          <h2>Coach decisions</h2>
          <DecisionBar counts={decisionCounts(review.moments)} />
        </div>
        {showAbility && (
          <div className="band-cell">
            <h2>Ability shape</h2>
            <AbilityCell review={review} />
          </div>
        )}
      </section>
      <div className="split">
        <div>
          <p className="scout-status">
            {phaseLabel(request)}
            {request?.progress?.message ? ` · ${request.progress.message}` : ""}
            {running && window && (
              <>
                {" · "}
                <button type="button" className="link" onClick={() => void cancel({ ...access, windowId: window.id as Id<"windows"> })}>Cancel</button>
              </>
            )}
          </p>
          {request?.errorMessage && request.status === "failed" && <p className="error">{request.errorMessage}</p>}
          {review.windows.length > 1 && (
            <div className="scout-filters">
              {review.windows.map((item) => (
                <button key={item.id} type="button" aria-pressed={item.id === window?.id} onClick={() => { setPlaying(null); setWindowId(item.id); }}>
                  Clip {item.order} · {clipTab(item, review.moments)}
                </button>
              ))}
            </div>
          )}
          <div className="stage">
            <div className="stage-frame">
              <video
                ref={videoRef}
                src={window ? `${API_ORIGIN}/api/videos/${window.videoKey}/media` : undefined}
                controls
                playsInline
                preload="auto"
                onLoadedMetadata={() => {
                  const target = pendingSeek.current;
                  if (target && videoRef.current && target.videoKey === window?.videoKey) {
                    pendingSeek.current = null;
                    videoRef.current.currentTime = target.startMs / 1000;
                    void videoRef.current.play();
                  }
                }}
                onTimeUpdate={() => boundary.current()}
              />
              <VideoOverlay videoRef={videoRef} frames={frames} selectedId={selectedId} moments={overlayMoments} />
            </div>
          </div>
          {clipMoments.filter((moment) => moment.status !== "rejected" && moment.status !== "stale").length === 0 && !running && (
            <p className="meta">{clipRun?.coverageNote || window?.noObservationReason || "No actions were counted on this clip."}</p>
          )}
          <ActionLanes
            moments={visible.filter((moment) => moment.videoKey === window?.videoKey)}
            durationMs={duration}
            missing={missing}
            videoRef={videoRef}
            onPlay={(id) => {
              const moment = review.moments.find((item) => item.id === id);
              if (moment) play([{ videoKey: moment.videoKey, startMs: moment.startMs, endMs: moment.endMs, moments: [] }]);
            }}
          />
          <div className="scout-filters">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={filter === item.id}
                onClick={() => setFilter((current) => (current === item.id ? "all" : item.id))}
              >
                {item.label}
              </button>
            ))}
            <button type="button" aria-pressed={reviewedOnly} onClick={() => setReviewedOnly((value) => !value)}>Coach-reviewed</button>
          </div>
        </div>
        <ul className="event-list">
          {listed.length === 0 && <li className="meta">No actions were counted on this clip.</li>}
          {listed.map((moment) => (
            <li key={moment.id}>
              <button type="button" className="event-main" onClick={() => play([{ videoKey: moment.videoKey, startMs: moment.startMs, endMs: moment.endMs, moments: [] }])}>
                <span className={`key ${moment.status === "suggestion" ? "outline" : moment.status}`} aria-hidden="true" />
                <span className="badge">Clip {moment.windowOrder}</span>
                <span className="badge">{sentence(moment.action ?? moment.category)}</span>
                <span className="num">{formatMs(moment.startMs)}</span>
                <span>{moment.visibleAction}</span>
              </button>
              <span className="meta">{(moment.outcomeDetail ?? moment.outcome).replaceAll("_", " ")} · {moment.status}</span>
              {moment.status === "suggestion" && (
                <span className="event-actions">
                  <button type="button" onClick={() => void acceptMoment(moment.id as Id<"observations">)}>Accept</button>
                  <button type="button" onClick={() => void decide({ ...access, observationId: moment.id as Id<"observations">, action: "reject", reason: "Not this action", reviewer })}>Reject</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {correction && window && (
        <section className="scout-next">
          <h2>Track lost</h2>
          <p className="scout-status">Track lost at {formatMs(correction.tMs)}. {correction.reason} Click the player.</p>
          <CorrectionFrame
            src={`${API_ORIGIN}/api/videos/${window.videoKey}/frames/${correction.frameId}?manifest=${window.manifestKey}`}
            boxes={correction.boxes}
            onPick={(next) => void correct(correction.frameId, next)}
          />
        </section>
      )}
      {message && <p className="error">{message}</p>}
      <OpportunityHandoff
        reviewId={review.submission.key}
        playerName={review.submission.player}
        stats={clipStats(review, trackedLabel)}
        profile={review.profile?.summary ?? ""}
      />
      <details>
        <summary>Diagnostics</summary>
        <p className="scout-status">
          {review.runs[0]?.coverageNote || "Coverage is reported when the analysis finishes."}
          {window?.spend ? ` Spend reconciled $${window.spend.reconciledUsd.toFixed(4)}.` : ""}
          {playlist.length ? ` ${playlistCount(playlist)} moments in this view.` : ""}
        </p>
      </details>
    </div>
  );
}

function sentence(value: string) {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function narrativeFindings(review: Review): { text: string; eventIds: string[] }[] {
  const raw = review.runs.find((run) => run.current)?.narrative;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { text: string; eventIds: string[] }[];
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch {
      /* the deterministic brief remains */
    }
  }
  return review.brief.findings;
}

function trackedSeconds(review: Review) {
  const current = review.runs.filter((run) => run.current);
  const measured = current.filter((run) => run.trackedMs != null);
  if (measured.length) return measured.reduce((sum, run) => sum + (run.trackedMs ?? 0), 0) / 1000;
  return current.reduce((sum, run) => {
    const match = run.coverageNote?.match(/Tracked ([0-9.]+)s/);
    return sum + (match ? Number(match[1]) : 0);
  }, 0);
}

function clipTab(item: Review["windows"][number], moments: Review["moments"]) {
  const status = item.requests[0]?.status;
  const count = moments.filter((moment) => moment.windowId === item.id && moment.status !== "rejected" && moment.status !== "stale").length;
  if (status === "queued" || status === "running") return "Analysing";
  if (status === "failed") return "Stopped";
  return `${count} events`;
}

function clipStats(review: Review, trackedLabel: string | undefined) {
  const moments = review.moments;
  const accepted = moments.filter((moment) => moment.status === "accepted");
  const pool = accepted.length
    ? accepted
    : moments.filter((moment) => moment.status === "suggestion" || moment.status === "held");
  const counts = countMoments(pool);
  const tracked = trackedLabel ? Number(trackedLabel) : 0;
  return {
    tracked_s: Number.isFinite(tracked) ? tracked : 0,
    receives: counts.receive,
    passes_completed: counts.passCompleted,
    passes_attempted: counts.pass,
    carries: counts.carry,
    losses: counts.loss,
    reviewed: accepted.length > 0,
    clips: Math.max(1, review.windows.length),
    confidence: review.confidence.score,
  };
}

function countMoments(moments: Review["moments"]) {
  const live = moments.filter((moment) => moment.status === "suggestion" || moment.status === "accepted" || moment.status === "held");
  const of = (action: string) => live.filter((moment) => moment.action === action);
  return {
    receive: of("receive").length,
    carry: of("carry").length,
    loss: of("loss").length,
    pass: of("pass").length,
    passCompleted: of("pass").filter((moment) => (moment.outcomeDetail ?? moment.outcome) === "completed" || moment.outcome === "completed_visible").length,
  };
}

function matches(moment: Moment, filter: FilterId, reviewedOnly: boolean) {
  if (moment.status === "rejected" || moment.status === "stale") return false;
  if (reviewedOnly && moment.status !== "accepted") return false;
  if (filter === "all") return true;
  if (filter === "unsuccessful") return UNSUCCESSFUL.has(moment.outcomeDetail ?? moment.outcome);
  if (filter === "unclear") return (moment.outcomeDetail ?? moment.outcome) === "unclear" || moment.outcome === "not_observable";
  return moment.action === filter;
}

function phaseLabel(request: Review["windows"][number]["requests"][number] | undefined) {
  if (!request) return "Waiting to start";
  const progress = request.progress;
  if (request.status === "queued") return "Queued";
  if (request.status === "succeeded") return "Analysis finished";
  if (request.status === "failed") return request.errorCode === "cancelled" ? "Cancelled" : "Partial result";
  if (progress?.phase === "tracking") return `Tracking ${progress.chunksDone ?? 0} of ${progress.chunksTotal ?? "?"} chunks`;
  if (progress?.phase === "inspecting") return `Inspecting ${progress.candidates ?? 0} candidate moments`;
  return request.stage ?? request.status;
}

function CorrectionFrame({
  src,
  boxes,
  onPick,
}: {
  src: string;
  boxes: { box: { x: number; y: number; w: number; h: number } }[];
  onPick: (box: { x: number; y: number; w: number; h: number }) => void;
}) {
  return <CorrectionImage key={src} src={src} boxes={boxes} onPick={onPick} />;
}

function CorrectionImage({
  src,
  boxes,
  onPick,
}: {
  src: string;
  boxes: { box: { x: number; y: number; w: number; h: number } }[];
  onPick: (box: { x: number; y: number; w: number; h: number }) => void;
}) {
  const [broken, setBroken] = useState(false);
  if (broken) return <p className="meta">The correction frame is not available yet. Reload in a moment.</p>;
  return (
    <div className="stage">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="The frame where the track was lost" onError={() => setBroken(true)} />
      {boxes.map((person, index) => (
        <button
          key={index}
          type="button"
          className="person"
          style={{ left: `${person.box.x * 100}%`, top: `${person.box.y * 100}%`, width: `${person.box.w * 100}%`, height: `${person.box.h * 100}%` }}
          aria-label={`Continue with detected player ${index + 1}`}
          onClick={() => onPick(person.box)}
        />
      ))}
    </div>
  );
}
