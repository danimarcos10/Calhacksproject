"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnchorCard, anchorFrom, draftFrom, type Draft } from "@/components/AnchorEditor";
import {
  API_ORIGIN,
  type Analysis,
  type Job,
  type Manifest,
  type ProviderStatus,
  type Revision,
  type VideoDetail,
  ApiError,
  formatMs,
  getJob,
  getReady,
  getVideo,
  proposeLocations,
  sampleWindow,
  saveTarget,
  startAnalysis,
  uploadClip,
} from "@/lib/api";
import { nextAttention, summaryLine } from "@/lib/attention";

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued",
  validating_input: "Validating",
  preparing_frames: "Sampling",
  estimating_cost: "Checking cost",
  analyzing: "Analyzing",
  validating_evidence: "Validating evidence",
  succeeded: "Complete",
  failed: "Failed",
  interrupted: "Interrupted",
};

const TERMINAL = new Set(["succeeded", "failed", "interrupted", "cancelled"]);

export function ReviewApp() {
  const router = useRouter();
  const params = useSearchParams();
  const videoId = params.get("video");
  const videoRef = useRef<HTMLVideoElement>(null);
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [message, setMessage] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [rights, setRights] = useState("");
  const [lengthSec, setLengthSec] = useState(8);
  const [startMs, setStartMs] = useState(0);
  const [playMs, setPlayMs] = useState(0);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [dirty, setDirty] = useState(false);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [jersey, setJersey] = useState("");
  const [teamColor, setTeamColor] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [attentionId, setAttentionId] = useState<string | null>(null);
  const [activeMs, setActiveMs] = useState<number | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    getReady().then((ready) => setProvider(ready.provider)).catch(() => setProvider(null));
  }, []);

  useEffect(() => {
    if (!videoId) {
      setVideo(null);
      return;
    }
    getVideo(videoId)
      .then((loaded) => {
        setVideo(loaded);
        const latest = loaded.manifests.at(-1) ?? null;
        const saved = loaded.revisions.at(-1) ?? null;
        setManifest(latest);
        setRevision(saved);
        setDraft(draftFrom(latest, saved));
        setDirty(false);
        setJersey(saved?.jersey_note ?? "");
        setTeamColor(saved?.team_color_note ?? "");
        if (latest) setStartMs(latest.start_ms);
      })
      .catch((error: Error) => setMessage(error.message));
  }, [videoId]);

  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const id = job.id;
    const timer = window.setInterval(() => {
      getJob(id).then(setJob).catch((error: Error) => setMessage(error.message));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  const endMs = startMs + lengthSec * 1000;
  const duration = video?.duration_ms ?? 0;

  function seek(ms: number) {
    const player = videoRef.current;
    if (!player) return;
    player.pause();
    player.currentTime = ms / 1000;
    setActiveMs(ms);
  }

  async function onUpload(file: File) {
    const extension = file.name.toLowerCase();
    if (!extension.endsWith(".mp4") && !extension.endsWith(".mov")) {
      setMessage("Upload an MP4 or MOV file.");
      return;
    }
    if (file.size > 200 * 1024 * 1024) {
      setMessage("Uploads are limited to 200 MB.");
      return;
    }
    setMessage("");
    setUploadProgress(0);
    try {
      const created = await uploadClip(file, rights, (fraction) => setUploadProgress(fraction));
      setUploadProgress(null);
      router.replace(`/?video=${created.id}`);
    } catch (error) {
      setUploadProgress(null);
      setMessage(error instanceof Error ? error.message : "The upload failed.");
    }
  }

  async function onSample() {
    if (!video) return;
    setBusy("Sampling frames");
    setMessage("");
    try {
      const sampled = await sampleWindow(video.id, startMs, Math.min(endMs, video.duration_ms));
      setManifest(sampled);
      setDraft(Object.fromEntries(sampled.frames.map((frame) => [frame.frame_id, { state: "unmarked" as const }])));
      setRevision(null);
      setDirty(true);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Sampling failed.");
    } finally {
      setBusy("");
    }
  }

  const changeDraft = useCallback((frameId: string, next: Draft[string]) => {
    setDraft((current) => ({ ...current, [frameId]: next }));
    setDirty(true);
  }, []);

  async function onSave() {
    if (!video || !manifest) return;
    const anchors = manifest.frames.flatMap((frame) => {
      const anchor = anchorFrom(frame.frame_id, draft[frame.frame_id]);
      return anchor ? [anchor] : [];
    });
    if (!anchors.some((anchor) => anchor.state === "located")) {
      setMessage("Mark the selected player on at least one frame.");
      return;
    }
    setBusy("Saving target");
    try {
      const saved = await saveTarget(video.id, {
        manifest_id: manifest.id,
        role: "",
        jersey_note: jersey,
        team_color_note: teamColor,
        note: "",
        anchors,
      });
      setRevision(saved);
      setDirty(false);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The target could not be saved.");
    } finally {
      setBusy("");
    }
  }

  async function onAnalyze() {
    if (!video || !manifest || !revision || dirty) return;
    setBusy("Starting analysis");
    setMessage("");
    try {
      const created = await startAnalysis(video.id, manifest.id, revision.id, crypto.randomUUID());
      setJob(created);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Analysis could not start.");
    } finally {
      setBusy("");
    }
  }

  async function onPropose() {
    if (!video || !manifest) return;
    const anchors = manifest.frames.flatMap((frame) => {
      const anchor = anchorFrom(frame.frame_id, draft[frame.frame_id]);
      return anchor ? [anchor] : [];
    });
    if (!anchors.some((anchor) => anchor.state === "located" && anchor.source !== "estimated")) {
      setMessage("Draw the player on at least one frame before proposing the rest.");
      return;
    }
    setBusy("Proposing locations");
    setMessage("");
    try {
      const proposed = await proposeLocations(video.id, { manifest_id: manifest.id, anchors });
      setDraft((current) => {
        const next = { ...current };
        for (const anchor of proposed.anchors) {
          const existing = next[anchor.frame_id];
          if (existing?.state === "located" && existing.source !== "estimated") continue;
          if (existing?.state === "not_visible") continue;
          next[anchor.frame_id] = {
            state: anchor.state,
            source: "estimated",
            box: anchor.box ?? undefined,
            method: anchor.method ?? undefined,
            reason: anchor.reason ?? undefined,
          };
        }
        return next;
      });
      setDirty(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Locations could not be proposed.");
    } finally {
      setBusy("");
    }
  }

  function focusFrame(frameId: string) {
    const frame = manifest?.frames.find((item) => item.frame_id === frameId);
    if (frame) seek(frame.source_t_ms);
    setAttentionId(frameId);
    document.getElementById(`frame-${frameId}`)?.scrollIntoView({ inline: "center", block: "nearest" });
  }

  const analysis: Analysis | null = job?.result ?? null;
  const synthetic = provider?.mode === "synthetic" || analysis?.provenance.provider_label === "synthetic";

  return (
    <main className="app">
      <header>
        <h1>SecondLook</h1>
        <p>Candidate observations stay tied to the clip. They are unreviewed suggestions, not ratings or odds.</p>
        <p className="meta">
          Single-clip workbench. Coaches review submissions in the <Link href="/review">review inbox</Link>.
        </p>
      </header>
      {synthetic && (
        <div className="banner" role="status">
          SYNTHETIC FIXTURE, not football analysis. This provider is only for plumbing tests.
        </div>
      )}
      {provider && !provider.configured && <div className="banner">{provider.detail}</div>}
      {message && <p className="error">{message}</p>}

      {!video && (
        <section className="panel upload">
          <h2>Upload a clip</h2>
          <p className="note">MP4 or MOV, up to 200 MB and 90 seconds.</p>
          <div className="row">
            <label>
              Rights note
              <input value={rights} onChange={(event) => setRights(event.target.value)} type="text" />
            </label>
            <input
              aria-label="Upload clip"
              type="file"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void onUpload(file);
              }}
            />
          </div>
          {uploadProgress !== null && (
            <p>{uploadProgress < 1 ? `Uploading ${Math.round(uploadProgress * 100)}%` : "Preparing a playable copy…"}</p>
          )}
        </section>
      )}

      {video && (
        <div className="workspace">
          <section className="panel">
            <video
              ref={videoRef}
              src={`${API_ORIGIN}${video.media_url}`}
              controls
              playsInline
              onTimeUpdate={(event) => setPlayMs(Math.round(event.currentTarget.currentTime * 1000))}
            />
            <div className="timeline" aria-hidden="true">
              <div className="window" style={{ left: pct(startMs, duration), width: pct(lengthSec * 1000, duration) }} />
              {analysis?.observations.map((observation) => (
                <div
                  key={observation.id}
                  className={activeMs === observation.start_ms ? "interval active" : "interval"}
                  style={{ left: pct(observation.start_ms, duration), width: pct(observation.end_ms - observation.start_ms, duration) }}
                />
              ))}
              <div className="playhead" style={{ left: pct(playMs, duration) }} />
            </div>
            <div className="controls">
              <span>{formatMs(playMs)} / {formatMs(duration)}</span>
              <button type="button" onClick={() => setStartMs(clampStart(playMs, lengthSec, duration))}>Use current time</button>
              <button type="button" onClick={() => setStartMs((value) => clampStart(value - 500, lengthSec, duration))}>−0.5s</button>
              <button type="button" onClick={() => setStartMs((value) => clampStart(value + 500, lengthSec, duration))}>+0.5s</button>
              {[6, 7, 8].map((seconds) => (
                <button key={seconds} type="button" aria-pressed={lengthSec === seconds} onClick={() => setLengthSec(seconds)}>
                  {seconds}s
                </button>
              ))}
              <span>Window {formatMs(startMs)}–{formatMs(Math.min(endMs, duration))}</span>
              <button type="button" onClick={() => void onSample()} disabled={Boolean(busy)}>Sample window</button>
            </div>
            {manifest && (
              <>
                <p className="note">{summaryLine(manifest.frames.map((frame) => draft[frame.frame_id] ?? { state: "unmarked" }))}</p>
                <div className="controls">
                  <button type="button" onClick={() => void onPropose()} disabled={Boolean(busy)}>Propose locations</button>
                  <button
                    type="button"
                    onClick={() => {
                      const frameId = nextAttention(manifest.frames.map((frame) => frame.frame_id), draft);
                      if (frameId) focusFrame(frameId);
                      else setMessage("No uncertain or in-between frame needs attention.");
                    }}
                  >
                    Next frame needing attention
                  </button>
                </div>
                {revision?.needs_review.map((reason) => (
                  <p key={reason} className="error">{reason}</p>
                ))}
                <div className="frames">
                  {manifest.frames.map((frame) => (
                    <AnchorCard
                      key={frame.frame_id}
                      frame={frame}
                      mark={draft[frame.frame_id] ?? { state: "unmarked" }}
                      attention={attentionId === frame.frame_id}
                      onChange={(next) => changeDraft(frame.frame_id, next)}
                    />
                  ))}
                </div>
                <div className="controls">
                  <label>
                    Jersey or number (optional, not used to identify the player)
                    <input value={jersey} onChange={(event) => { setJersey(event.target.value); setDirty(true); }} type="text" />
                  </label>
                  <label>
                    Team colour (optional, not used to identify the player)
                    <input value={teamColor} onChange={(event) => { setTeamColor(event.target.value); setDirty(true); }} type="text" />
                  </label>
                  <button type="button" onClick={() => void onSave()} disabled={Boolean(busy)}>Save target</button>
                  <span>{revision && !dirty ? `Revision ${revision.revision}` : "Target not saved"}</span>
                </div>
              </>
            )}
          </section>
          <aside className="panel">
            <h2>Evidence</h2>
            <button type="button" className="primary" onClick={() => void onAnalyze()} disabled={!revision || dirty || Boolean(busy) || (job ? !TERMINAL.has(job.status) : false)}>
              Run analysis
            </button>
            {job && (
              <div>
                <p><strong>{STAGE_LABEL[job.stage] ?? job.stage}</strong> {job.cache_status === "cached" ? "· Cached result" : ""}</p>
                <ol className="meta">
                  {job.stage_log.map((entry, index) => (
                    <li key={`${entry.stage}-${index}`}>
                      {STAGE_LABEL[entry.stage] ?? entry.stage}
                      {entry.at ? ` · ${entry.at.slice(11, 19)}` : ""}
                    </li>
                  ))}
                </ol>
                {job.error && (
                  <p className="error">
                    {job.error.user_message}
                    {job.error.retryable && (
                      <>
                        {" "}
                        <button type="button" onClick={() => void onAnalyze()}>Retry</button>
                      </>
                    )}
                  </p>
                )}
              </div>
            )}
            <div className="cards">
              {analysis?.observations.map((observation) => (
                <div
                  key={observation.id}
                  role="button"
                  tabIndex={0}
                  className={activeMs === observation.seek_ms ? "card selected" : "card"}
                  data-seek-ms={observation.seek_ms}
                  onClick={() => seek(observation.seek_ms)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      seek(observation.seek_ms);
                    }
                  }}
                >
                  <h3>{label(observation.category)}</h3>
                  <p>{observation.visible_action}</p>
                  <p>{formatMs(observation.start_ms)}–{formatMs(observation.end_ms)}</p>
                  <p>Outcome: {label(observation.outcome)}</p>
                  <span className="tag">Candidate, unreviewed</span>
                  <span className="tag">{provenanceLabel(analysis)}</span>
                  {observation.attribution_hold && <span className="tag hold">Held: {observation.hold_reason}</span>}
                  {observation.hold_frame_id && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        focusFrame(observation.hold_frame_id as string);
                      }}
                    >
                      Open {observation.hold_frame_id}
                    </button>
                  )}
                  {observation.limitations[0] && <p className="meta">{observation.limitations[0]}</p>}
                </div>
              ))}
            </div>
            {analysis && analysis.observations.length === 0 && (
              <p>{analysis.no_observation_reason || "No supported observation in this window."}</p>
            )}
            {analysis?.gaps.map((gap) => <p key={gap} className="meta">Gap: {gap}</p>)}
            {analysis?.validation_issues.map((issue, index) => (
              <p key={index} className="meta">Not shown: {issue.message}</p>
            ))}
            {analysis && (
              <p className="meta">
                {provenanceLabel(analysis)} · {analysis.provenance.model_returned || analysis.provenance.model_requested} · {analysis.provenance.prompt_version}
                {analysis.provenance.usage.input_tokens != null && ` · ${analysis.provenance.usage.input_tokens}+${analysis.provenance.usage.output_tokens ?? 0} tokens`}
                {analysis.provenance.cost_usd != null && ` · $${analysis.provenance.cost_usd.toFixed(4)}`}
                {analysis.provenance.latency_ms != null && ` · ${(analysis.provenance.latency_ms / 1000).toFixed(1)}s`}
                {analysis.provenance.cache_status === "cached" ? " · cached" : ""}
              </p>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}

function provenanceLabel(analysis: Analysis) {
  if (analysis.provenance.provider_label === "synthetic") return "synthetic";
  return analysis.provenance.cache_status === "cached" ? "live Claude · cached" : "live Claude";
}

function clampStart(value: number, lengthSec: number, duration: number) {
  const max = Math.max(0, duration - lengthSec * 1000);
  return Math.min(max, Math.max(0, Math.round(value)));
}

function pct(value: number, duration: number) {
  if (!duration) return "0%";
  return `${Math.min(100, Math.max(0, (value / duration) * 100))}%`;
}

function label(value: string) {
  return value.replaceAll("_", " ");
}
