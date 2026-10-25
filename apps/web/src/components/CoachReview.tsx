"use client";

import Link from "next/link";
import { useMutation, useQuery } from "convex/react";
import type { FunctionReturnType } from "convex/server";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../../convex/_generated/api";
import type { Id } from "../../convex/_generated/dataModel";
import { categoryLabel } from "../../convex/lib/summary";
import { API_ORIGIN, formatMs } from "@/lib/api";
import { CONTEXT_PAD_MS, STATUS_LABEL, buildPlaylist, playlistCount, playlistMs, type PlaylistMode, type Segment } from "@/lib/moments";
import { codeFor, errorText, forgetCode, rememberCode, reviewerName, setReviewerName } from "@/lib/reviewAccess";
import { Bar, DecisionBar } from "@/components/Charts";
import { ClipWell } from "@/components/ClipWell";
import { decisionCounts, share } from "@/lib/visual";
import { useCue, useWorking } from "@/components/Look";
import { ScoutBoard } from "@/components/ScoutBoard";
import { useScreenScope } from "@/components/Shell";

type Review = FunctionReturnType<typeof api.review.get>;
type Moment = Review["moments"][number];
type ReviewWindow = Review["windows"][number];

export function CoachReviewRoute() {
  const { id } = useParams<{ id: string }>();
  return <CoachReview submissionKey={id} />;
}

export function CoachReview({ submissionKey }: { submissionKey: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [code, setCode] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useWorking(!ready);

  useEffect(() => {
    const fromUrl = params.get("code");
    if (fromUrl) {
      rememberCode(submissionKey, fromUrl);
      router.replace(`/review/${submissionKey}`);
    }
    setCode(fromUrl ?? codeFor(submissionKey));
    setReady(true);
  }, [params, router, submissionKey]);

  if (!ready) return (
    <main className="screen">
      <header className="title-row">
        <div>
          <h1>SecondLook review</h1>
          <p className="sub">Opening this submission.</p>
        </div>
      </header>
      <div className="sheet sheet-empty">
        <ClipWell />
      </div>
    </main>
  );
  if (!code) {
    return (
      <CodeGate
        onCode={(value) => {
          rememberCode(submissionKey, value);
          setCode(value);
        }}
      />
    );
  }
  return (
    <AccessBoundary
      key={code}
      onReset={() => {
        forgetCode(submissionKey);
        setCode(null);
      }}
    >
      <ReviewBody submissionKey={submissionKey} code={code} />
    </AccessBoundary>
  );
}

function CodeGate({ onCode, message }: { onCode: (code: string) => void; message?: string }) {
  const [value, setValue] = useState("");
  return (
    <main className="screen">
      <header className="title-row">
        <div>
        <h1>SecondLook review</h1>
        <p className="sub">Each submission opens with its own review code.</p>
        </div>
      </header>
      <section className="panel upload">
        {message && <p className="error">{message}</p>}
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) onCode(value.trim());
          }}
        >
          <label>
            Review code
            <input type="text" value={value} onChange={(event) => setValue(event.target.value)} />
          </label>
          <button type="submit" className="primary">Open</button>
        </form>
        <p className="meta"><Link href="/review">Back to the review inbox</Link></p>
      </section>
    </main>
  );
}

class AccessBoundary extends Component<{ children: ReactNode; onReset: () => void }, { error: unknown }> {
  state = { error: null as unknown };
  static getDerivedStateFromError(error: unknown) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <main className="screen">
          <section className="panel upload">
            <p className="error">{errorText(this.state.error, "The review could not be loaded. Check that Convex is running.")}</p>
            <button type="button" onClick={this.props.onReset}>Enter a different code</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function ReviewBody({ submissionKey, code }: { submissionKey: string; code: string }) {
  const review = useQuery(api.review.get, { key: submissionKey, code });
  const [reviewer, setReviewer] = useState("Coach");
  useScreenScope(review?.submission.player ?? "No submission open");
  useEffect(() => setReviewer(reviewerName()), []);

  if (review === undefined) {
    return (
      <main className="screen">
        <div className="skeleton skel-title" />
        <div className="skeleton skel-line" />
        <div className="skeleton skel-block" />
      </main>
    );
  }
  const scout = review.windows.some((item) => item.kind === "scout");
  if (scout) {
    return (
      <main className="screen">
        <ScoutBoard review={review} access={{ key: submissionKey, code }} reviewer={reviewer} />
      </main>
    );
  }
  return (
    <main className="screen review">
      <header className="review-head">
        <div>
          <h1>{review.submission.player}</h1>
          <p className="sub">{review.submission.title}</p>
          <p className="meta">Rights: {review.submission.rightsNote}</p>
        </div>
        <label className="reviewer">
          Display name (not an account)
          <input
            type="text"
            value={reviewer}
            onChange={(event) => {
              setReviewer(event.target.value);
              setReviewerName(event.target.value);
            }}
          />
        </label>
      </header>
      <Workspace review={review} access={{ key: submissionKey, code }} reviewer={reviewer} />
    </main>
  );
}

type Access = { key: string; code: string };
type Playing = { mode: PlaylistMode | "single"; index: number; segments: Segment[] };

function Workspace({ review, access, reviewer }: { review: Review; access: Access; reviewer: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pendingSeek = useRef<Segment | null>(null);
  const firstVideo = review.windows[0]?.videoKey ?? "";
  const [videoKey, setVideoKey] = useState(firstVideo);
  const [play, setPlay] = useState<Playing | null>(null);
  const [nowMs, setNowMs] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const durations = useMemo(
    () => Object.fromEntries(review.windows.map((w) => [w.videoKey, w.videoDurationMs])),
    [review.windows],
  );
  const current = review.moments.filter((m) => m.status === "suggestion" || m.status === "held" || m.status === "accepted");
  const history = review.moments.filter((m) => m.status === "rejected" || m.status === "stale");
  const allSegments = useMemo(() => buildPlaylist(review.moments, "current", durations), [review.moments, durations]);
  const acceptedSegments = useMemo(() => buildPlaylist(review.moments, "accepted", durations), [review.moments, durations]);
  const duration = durations[videoKey] ?? 0;

  function startSegment(segments: Segment[], index: number, mode: Playing["mode"]) {
    const segment = segments[index];
    const player = videoRef.current;
    if (!segment || !player) return;
    setPlay({ segments, index, mode });
    if (segment.videoKey !== videoKey) {
      pendingSeek.current = segment;
      setVideoKey(segment.videoKey);
      return;
    }
    player.currentTime = segment.startMs / 1000;
    void player.play();
  }

  const boundary = useRef<() => boolean>(() => false);
  boundary.current = () => {
    const player = videoRef.current;
    const segment = play ? play.segments[play.index] : null;
    if (!play || !player || !segment || segment.videoKey !== videoKey || player.currentTime * 1000 < segment.endMs) return false;
    if (play.index + 1 < play.segments.length) startSegment(play.segments, play.index + 1, play.mode);
    else {
      player.pause();
      setPlay(null);
    }
    return true;
  };

  // Animation frames give a tight stop while the tab is visible; timeupdate
  // still fires when the browser throttles animation frames in the background.
  useEffect(() => {
    if (!play) return;
    let frame = 0;
    const tick = () => {
      if (!boundary.current()) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [play, videoKey]);

  function playMoment(moment: Moment) {
    setSelected(moment.id);
    const [segment] = buildPlaylist([{ ...moment, status: "accepted" }], "accepted", durations);
    if (segment) startSegment([segment], 0, "single");
  }

  function stop() {
    videoRef.current?.pause();
    setPlay(null);
  }

  const segment = play ? play.segments[play.index] : null;
  const inside = segment?.moments.find((m) => nowMs >= m.startMs && nowMs <= m.endMs) ?? null;

  return (
    <div className="workspace">
      <section className="panel">
        <video
          ref={videoRef}
          src={videoKey ? `${API_ORIGIN}/api/videos/${videoKey}/media` : undefined}
          controls
          playsInline
          preload="auto"
          onLoadedMetadata={() => {
            const target = pendingSeek.current;
            if (target && videoRef.current) {
              pendingSeek.current = null;
              videoRef.current.currentTime = target.startMs / 1000;
              void videoRef.current.play();
            }
          }}
          onTimeUpdate={(event) => {
            setNowMs(Math.round(event.currentTarget.currentTime * 1000));
            boundary.current();
          }}
        />
        <div className="timeline" aria-hidden="true">
          {review.windows
            .filter((w) => w.videoKey === videoKey)
            .map((w) => (
              <div key={w.id} className="window" style={{ left: pct(w.startMs, duration), width: pct(w.endMs - w.startMs, duration) }} />
            ))}
          {current
            .filter((m) => m.videoKey === videoKey)
            .map((m) => (
              <div
                key={m.id}
                className={`interval ${m.status}${inside?.id === m.id ? " active" : ""}`}
                style={{ left: pct(m.startMs, duration), width: pct(Math.max(m.endMs - m.startMs, 120), duration) }}
              />
            ))}
          <div className="playhead" style={{ left: pct(nowMs, duration) }} />
        </div>
        <div className="controls">
          <button type="button" className="primary" disabled={!allSegments.length} onClick={() => startSegment(allSegments, 0, "current")}>
            Watch moments ({playlistCount(allSegments)})
          </button>
          <button type="button" disabled={!acceptedSegments.length} onClick={() => startSegment(acceptedSegments, 0, "accepted")}>
            Watch accepted only ({playlistCount(acceptedSegments)})
          </button>
          <button type="button" disabled={!play} onClick={stop}>Stop</button>
          <span className="meta" data-testid="now-ms">Now {formatMs(nowMs)}</span>
        </div>
        <p className="meta" data-testid="segment-status">
          {segment
            ? `Segment ${play!.index + 1} of ${play!.segments.length} plays ${formatMs(segment.startMs)}–${formatMs(segment.endMs)} ` +
              `(evidence ${segment.moments.map((m) => `${formatMs(m.startMs)}–${formatMs(m.endMs)}`).join(", ")}, ` +
              `±${(CONTEXT_PAD_MS / 1000).toFixed(1)} s context)` +
              (inside ? " · inside the evidence interval" : " · context")
            : `Playlist: all current moments ${(playlistMs(allSegments) / 1000).toFixed(1)} s, accepted only ${(playlistMs(acceptedSegments) / 1000).toFixed(1)} s, including ±${(CONTEXT_PAD_MS / 1000).toFixed(1)} s context. Seeks the source video; no export.`}
        </p>

        <h2>Moments</h2>
        {current.length === 0 && (
          <p className="meta">No current moment. Windows without analysis are listed under Windows; analyse them to get suggestions.</p>
        )}
        <div className="cards">
          {current.map((moment) => (
            <MomentCard
              key={moment.id}
              moment={moment}
              access={access}
              reviewer={reviewer}
              selected={selected === moment.id}
              playing={inside?.id === moment.id}
              onPlay={() => playMoment(moment)}
            />
          ))}
        </div>
        {history.length > 0 && (
          <details className="history">
            <summary>History: {history.length} rejected or stale {history.length === 1 ? "moment" : "moments"} (kept, not in the playlist or summary)</summary>
            <div className="cards">
              {history.map((moment) => (
                <MomentCard
                  key={moment.id}
                  moment={moment}
                  access={access}
                  reviewer={reviewer}
                  selected={selected === moment.id}
                  playing={inside?.id === moment.id}
                  onPlay={() => playMoment(moment)}
                />
              ))}
            </div>
          </details>
        )}
        <WindowsPanel review={review} access={access} reviewer={reviewer} />
      </section>
      <aside className="panel">
        <SummaryPanel review={review} access={access} reviewer={reviewer} onOpen={(id) => {
          const moment = review.moments.find((m) => m.id === id);
          if (moment) playMoment(moment);
        }} />
      </aside>
    </div>
  );
}

function MomentCard({
  moment,
  access,
  reviewer,
  selected,
  playing,
  onPlay,
}: {
  moment: Moment;
  access: Access;
  reviewer: string;
  selected: boolean;
  playing: boolean;
  onPlay: () => void;
}) {
  const decide = useMutation(api.review.decide);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const cue = useCue();
  useWorking(saving !== "");

  async function send(action: "accept" | "reject" | "reset") {
    setSaving(action === "accept" ? "Saving accept…" : action === "reject" ? "Saving reject…" : "Saving undo…");
    setError("");
    try {
      await decide({ ...access, observationId: moment.id as Id<"observations">, action, reason: action === "reject" ? reason : undefined, reviewer });
      if (action === "accept") cue("nod");
      setRejecting(false);
      setReason("");
    } catch (caught) {
      setError(errorText(caught, "The decision was not saved."));
    } finally {
      setSaving("");
    }
  }

  const live = moment.status !== "stale";
  return (
    <div className={`card status-${moment.status}${selected ? " selected" : ""}${playing ? " playing" : ""}`} data-moment={moment.id}>
      <div className="card-head">
        <h3>{categoryLabel(moment.category)}</h3>
        <span className={`status ${moment.status}`}>{STATUS_LABEL[moment.status]}</span>
      </div>
      <p>{moment.visibleAction}</p>
      <p className="meta">
        Window {moment.windowOrder} · evidence {formatMs(moment.startMs)}–{formatMs(moment.endMs)} · outcome {moment.outcome.replaceAll("_", " ")} · selection {moment.revisionNumber}
      </p>
      {moment.status === "held" && moment.holdReason && <p className="tag hold">Identity hold: {moment.holdReason}</p>}
      {moment.status === "stale" && (
        <p className="meta">Made for player selection {moment.revisionNumber}, which was corrected. Kept in history only.</p>
      )}
      {moment.limitations[0] && <p className="meta">Limit: {moment.limitations[0]}</p>}
      {moment.decision && (
        <p className="meta">
          {moment.decision.action === "reset" ? "Reset to suggestion" : moment.decision.action === "accept" ? "Accepted" : "Rejected"} by {moment.decision.reviewer} at{" "}
          {new Date(moment.decision.at).toLocaleTimeString()}
          {moment.decision.reason ? ` · “${moment.decision.reason}”` : ""}
        </p>
      )}
      <div className="actions">
        <button type="button" onClick={onPlay}>Play</button>
        {live && moment.status === "suggestion" && (
          <button type="button" disabled={Boolean(saving)} onClick={() => void send("accept")}>Accept</button>
        )}
        {live && moment.status !== "rejected" && (
          <button type="button" disabled={Boolean(saving)} onClick={() => setRejecting((value) => !value)}>Reject</button>
        )}
        {live && (moment.status === "accepted" || moment.status === "rejected") && (
          <button type="button" disabled={Boolean(saving)} onClick={() => void send("reset")}>
            {moment.status === "accepted" ? "Undo accept" : "Restore"}
          </button>
        )}
        {live && (
          <Link className="button" href={`/prepare/${access.key}/${moment.windowOrder}?mode=correction`}>Correct player</Link>
        )}
      </div>
      {rejecting && (
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            void send("reject");
          }}
        >
          <input type="text" placeholder="Reason (optional)" value={reason} onChange={(event) => setReason(event.target.value)} />
          <button type="submit" disabled={Boolean(saving)}>Confirm reject</button>
        </form>
      )}
      {saving && <p className="meta pending">{saving}</p>}
      {error && <p className="error">{error}</p>}
      {moment.history.length > 1 && (
        <p className="meta">Decision trail: {moment.history.map((d) => `${d.action} (${d.reviewer})`).join(" → ")}</p>
      )}
    </div>
  );
}

function SummaryPanel({ review, access, reviewer, onOpen }: { review: Review; access: Access; reviewer: string; onOpen: (id: string) => void }) {
  const summary = review.summary;
  const saveFootage = useMutation(api.review.saveFootageRequest);
  const saveNote = useMutation(api.review.saveNote);
  return (
    <div className="summary">
      <h2>Summary</h2>
      <p className="meta">Built from saved decisions with a fixed template. No extra model call.</p>
      <DecisionBar counts={decisionCounts(review.moments)} />
      <h3>Accepted</h3>
      {summary.accepted.length === 0 && <p className="meta">Nothing accepted yet.</p>}
      {summary.accepted.map((group) => (
        <div key={group.category} className="group">
          <h4>{group.label} ({group.moments.length})</h4>
          <ul>
            {group.moments.map((m) => (
              <li key={m.id}>
                <button type="button" className="link" onClick={() => onOpen(m.id)}>
                  W{m.windowOrder} {formatMs(m.startMs)}–{formatMs(m.endMs)}
                </button>{" "}
                {m.visibleAction}
              </li>
            ))}
          </ul>
        </div>
      ))}
      <h3>Pending ({summary.pending.length})</h3>
      <ul>
        {summary.pending.map((m) => (
          <li key={m.id}>
            <button type="button" className="link" onClick={() => onOpen(m.id)}>
              {categoryLabel(m.category)} W{m.windowOrder} {formatMs(m.startMs)}
            </button>{" "}
            {m.status === "held" ? "identity hold" : "AI suggestion"}
          </li>
        ))}
      </ul>
      <h3>What this footage does not establish</h3>
      <ul>
        {summary.notEstablished.map((line) => <li key={line}>{line}</li>)}
      </ul>
      <SavedText
        title="Next footage request"
        saved={review.footageRequest}
        initial={review.footageRequest?.body ?? summary.suggestedFootageRequest}
        suggestion={review.footageRequest ? null : "Suggested from the gaps above. Edit, then save."}
        save={saveFootage}
        access={access}
        reviewer={reviewer}
      />
      <SavedText
        title="Coach note"
        saved={review.note}
        initial={review.note?.body ?? ""}
        suggestion={null}
        save={saveNote}
        access={access}
        reviewer={reviewer}
      />
      <h3>Coverage</h3>
      <p>
        Analysed footage: <strong>{(summary.analysedMs / 1000).toFixed(1)} s</strong> · Moments shortlist:{" "}
        <strong>{(summary.shortlistMs / 1000).toFixed(1)} s</strong>
      </p>
      <Bar value={share(summary.shortlistMs, summary.analysedMs)} />
      <p className="meta">Coverage, not time saved. The shortlist is the exact evidence time of current moments, before playback context.</p>
      <PrepPanel review={review} />
    </div>
  );
}

function SavedText({
  title,
  saved,
  initial,
  suggestion,
  save,
  access,
  reviewer,
}: {
  title: string;
  saved: { body: string; reviewer: string; at: number } | null;
  initial: string;
  suggestion: string | null;
  save: (args: Access & { body: string; reviewer: string }) => Promise<unknown>;
  access: Access;
  reviewer: string;
}) {
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!touched) setDraft(initial);
  }, [initial, touched]);
  const dirty = touched && draft.trim() !== (saved?.body ?? "");
  return (
    <div className="saved-text">
      <h3>{title}</h3>
      <textarea
        aria-label={title}
        rows={4}
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          setTouched(true);
        }}
      />
      <div className="row">
        <button
          type="button"
          disabled={busy || (!dirty && Boolean(saved))}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await save({ ...access, body: draft, reviewer });
              setTouched(false);
            } catch (caught) {
              setError(errorText(caught, "Not saved."));
            } finally {
              setBusy(false);
            }
          }}
        >
          Save
        </button>
        {dirty && <span className="tag pending">Unsaved edits</span>}
        {!dirty && saved && <span className="meta">Saved by {saved.reviewer} at {new Date(saved.at).toLocaleTimeString()}</span>}
        {!saved && suggestion && <span className="meta">{suggestion}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function count(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

function PrepPanel({ review }: { review: Review }) {
  const totals = review.windows.reduce(
    (sum, w) => ({
      manual: sum.manual + w.prep.manualBoxes,
      confirmed: sum.confirmed + w.prep.confirmedEstimates,
      hidden: sum.hidden + w.prep.notVisibleMarks,
      saves: sum.saves + w.prep.saves,
      corrections: sum.corrections + w.prep.corrections,
      frames: sum.frames + w.prep.framesSampled,
      estimated: sum.estimated + w.prep.estimatedBoxes,
      offered: sum.offered + w.prep.proposalsOffered,
      kept: sum.kept + w.prep.proposalsKept,
    }),
    { manual: 0, confirmed: 0, hidden: 0, saves: 0, corrections: 0, frames: 0, estimated: 0, offered: 0, kept: 0 },
  );
  const latency = review.runs.filter((r) => r.current && r.latencyMs != null).reduce((sum, r) => sum + (r.latencyMs ?? 0), 0);
  return (
    <div className="prep">
      <h3>Preparation effort</h3>
      <p>
        <strong>Human:</strong> {count(totals.manual, "box", "boxes")} drawn by hand, {count(totals.confirmed, "estimate")} confirmed,{" "}
        {count(totals.hidden, "not-visible mark")}, {count(totals.saves, "saved selection")} ({count(totals.corrections, "correction")}). Each
        window also needed an explicit link to this player.
      </p>
      <p>
        <strong>Automatic:</strong> {count(totals.frames, "frame")} sampled, {count(totals.offered, "tracker estimate")} offered ({totals.kept} kept),{" "}
        {count(totals.estimated, "estimated box", "estimated boxes")} in current selections, model time {(latency / 1000).toFixed(1)} s for current analyses.
      </p>
      {review.windows.some((w) => w.prep.importedFromM0) && (
        <p className="meta">Some selections were imported from the single-clip workbench, where the boxes were drawn by hand.</p>
      )}
    </div>
  );
}

function WindowsPanel({ review, access, reviewer }: { review: Review; access: Access; reviewer: string }) {
  const queueOne = useMutation(api.review.queueAnalysis);
  const queueAll = useMutation(api.review.queueAll);
  const [message, setMessage] = useState("");

  async function run(task: () => Promise<unknown>, done: string) {
    setMessage("");
    try {
      await task();
      setMessage(done);
    } catch (caught) {
      setMessage(errorText(caught, "Not queued."));
    }
  }

  return (
    <div className="windows">
      <div className="card-head">
        <h2>Windows</h2>
        <button type="button" onClick={() => void run(() => queueAll({ ...access, reviewer }), "Prepared windows queued in order.")}>
          Analyse all prepared windows
        </button>
      </div>
      {message && <p className="meta">{message}</p>}
      {review.windows.map((w) => (
        <WindowRow key={w.id} window={w} review={review} onQueue={() => void run(() => queueOne({ ...access, windowId: w.id, reviewer }), `Window ${w.order} queued.`)} access={access} />
      ))}
      <h3>Analysis history and cost</h3>
      <ul className="runs">
        {review.runs.map((r) => (
          <li key={r.id}>
            W{r.windowOrder} selection {r.revisionNumber} · {r.current ? "current" : r.outdatedOnArrival ? "arrived after a correction" : "stale"} ·{" "}
            {r.providerLabel === "synthetic" ? "synthetic fixture" : r.model} · {count(r.observationCount, "observation")} ·{" "}
            {r.cacheStatus === "cached" ? "cached result, no new charge" : "live call"}
            {r.costUsd != null ? ` · original call $${r.costUsd.toFixed(4)}` : " · cost unknown"}
            {r.inputTokens != null ? ` · ${r.inputTokens}+${r.outputTokens ?? 0} tokens` : " · usage unknown"}
            {r.latencyMs != null ? ` · ${(r.latencyMs / 1000).toFixed(1)} s` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WindowRow({ window: w, review, onQueue, access }: { window: ReviewWindow; review: Review; onQueue: () => void; access: Access }) {
  const latest = w.requests[0];
  const analysed = w.currentRunId !== null;
  const run = review.runs.find((r) => r.id === w.currentRunId);
  let status = "Not prepared: no player selection yet";
  if (w.currentRevision > 0) status = analysed ? "Analysed for the current selection" : "Prepared, not analysed";
  if (latest && latest.revisionNumber === w.currentRevision) {
    if (latest.status === "queued") status = "Queued";
    if (latest.status === "running") status = `Running: ${latest.stage ?? "claimed"} (attempt ${latest.attempt})`;
    if (latest.status === "failed") status = `Failed: ${latest.errorMessage ?? latest.errorCode}`;
  }
  const busy = latest && latest.revisionNumber === w.currentRevision && (latest.status === "queued" || latest.status === "running");
  useWorking(Boolean(busy));
  return (
    <div className="window-row" data-window={w.order}>
      <p>
        <strong>Window {w.order}</strong> {formatMs(w.startMs)}–{formatMs(w.endMs)} · {w.frames.length} frames ·{" "}
        {w.revision ? `selection ${w.revision.number} (${w.revision.origin}, saved by ${w.revision.savedBy})` : "no selection"}
      </p>
      <p className={latest?.status === "failed" ? "error" : "meta"}>
        {status}
        {run && analysed ? ` · ${count(run.observationCount, "observation")}${run.cacheStatus === "cached" ? " · cached result" : ""}` : ""}
      </p>
      <p className="meta">Linked to this player by {w.link.assertedBy}: “{w.link.statement}”</p>
      {w.spend && (
        <p className="meta">
          Window spend so far: ${w.spend.reconciledUsd.toFixed(4)} across {count(w.spend.liveCalls, "live call")} ·{" "}
          {count(w.spend.cachedReuses, "cached reuse")} · {count(w.spend.failedJobs, "failed job")} ·{" "}
          {count(w.spend.unknownUsageAttempts, "attempt")} with unknown usage (cost not reported)
        </p>
      )}
      <div className="actions">
        <button type="button" disabled={w.currentRevision < 1 || analysed || Boolean(busy)} onClick={onQueue}>
          {latest?.status === "failed" && latest.revisionNumber === w.currentRevision ? "Retry analysis" : "Analyse"}
        </button>
        <Link className="button" href={`/prepare/${access.key}/${w.order}`}>
          {w.currentRevision > 0 ? "Edit player selection" : "Prepare window"}
        </Link>
      </div>
    </div>
  );
}

function pct(value: number, duration: number) {
  if (!duration) return "0%";
  return `${Math.min(100, Math.max(0, (value / duration) * 100))}%`;
}
