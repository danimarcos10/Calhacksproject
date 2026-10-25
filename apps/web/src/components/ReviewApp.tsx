"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_ORIGIN,
  type Analysis,
  type Anchor,
  type Frame,
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
  sampleWindow,
  saveTarget,
  startAnalysis,
  uploadClip,
} from "@/lib/api";
import { boxFromPoints, clampToImage, containFit, cssToNormalized, normalizedToCss, type Box } from "@/lib/geometry";

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

type Draft = Record<string, { state: "box" | "not_visible" | "unmarked"; box?: Box }>;

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
  const [uncertain, setUncertain] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
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
        setUncertain(saved?.identity_uncertain ?? false);
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
    const anchors: Anchor[] = manifest.frames
      .map((frame) => ({ frame, mark: draft[frame.frame_id] }))
      .filter((item) => item.mark && item.mark.state !== "unmarked")
      .map((item) =>
        item.mark.state === "box"
          ? { frame_id: item.frame.frame_id, state: "box" as const, box: item.mark.box }
          : { frame_id: item.frame.frame_id, state: "not_visible" as const },
      );
    if (!anchors.some((anchor) => anchor.state === "box")) {
      setMessage("Mark the target on at least one frame.");
      return;
    }
    setBusy("Saving target");
    try {
      const saved = await saveTarget(video.id, {
        manifest_id: manifest.id,
        role: "fullback",
        jersey_note: jersey,
        team_color_note: teamColor,
        identity_uncertain: uncertain,
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

  function markRestNotVisible() {
    if (!manifest) return;
    setDraft((current) => {
      const next = { ...current };
      for (const frame of manifest.frames) {
        if (!next[frame.frame_id] || next[frame.frame_id].state === "unmarked") {
          next[frame.frame_id] = { state: "not_visible" };
        }
      }
      return next;
    });
    setDirty(true);
  }

  const analysis: Analysis | null = job?.result ?? null;
  const synthetic = provider?.mode === "synthetic" || analysis?.provenance.provider_label === "synthetic";

  return (
    <main className="app">
      <header>
        <h1>SecondLook</h1>
        <p>Candidate observations stay tied to the clip. They are unreviewed suggestions, not ratings or odds.</p>
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
                <div className="frames">
                  {manifest.frames.map((frame) => (
                    <AnchorCard
                      key={frame.frame_id}
                      frame={frame}
                      mark={draft[frame.frame_id] ?? { state: "unmarked" }}
                      onChange={(next) => changeDraft(frame.frame_id, next)}
                    />
                  ))}
                </div>
                <div className="controls">
                  <button type="button" onClick={markRestNotVisible}>Not visible on the rest</button>
                  <label>
                    Jersey note
                    <input value={jersey} onChange={(event) => { setJersey(event.target.value); setDirty(true); }} type="text" />
                  </label>
                  <label>
                    Team colour
                    <input value={teamColor} onChange={(event) => { setTeamColor(event.target.value); setDirty(true); }} type="text" />
                  </label>
                  <label>
                    <input type="checkbox" checked={uncertain} onChange={(event) => { setUncertain(event.target.checked); setDirty(true); }} />
                    Identity uncertain
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
                <button
                  key={observation.id}
                  type="button"
                  className={activeMs === observation.start_ms ? "card selected" : "card"}
                  data-start-ms={observation.start_ms}
                  onClick={() => seek(observation.start_ms)}
                >
                  <h3>{label(observation.category)}</h3>
                  <p>{observation.visible_action}</p>
                  <p>{formatMs(observation.start_ms)}–{formatMs(observation.end_ms)}</p>
                  <p>Outcome: {label(observation.outcome)}</p>
                  <span className="tag">Candidate, unreviewed</span>
                  {observation.attribution_hold && <span className="tag hold">Attribution withheld</span>}
                  {observation.limitations[0] && <p className="meta">{observation.limitations[0]}</p>}
                </button>
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
                {analysis.provenance.model_returned || analysis.provenance.model_requested} · {analysis.provenance.prompt_version}
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

function AnchorCard({ frame, mark, onChange }: { frame: Frame; mark: Draft[string]; onChange: (next: Draft[string]) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    if (!canvas || !image) return;
    const cssWidth = canvas.clientWidth;
    const cssHeight = canvas.clientHeight;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(cssWidth * ratio);
    canvas.height = Math.round(cssHeight * ratio);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.fillStyle = "#0b1220";
    context.fillRect(0, 0, cssWidth, cssHeight);
    const fit = containFit(frame.width, frame.height, cssWidth, cssHeight);
    context.drawImage(image, fit.offsetX, fit.offsetY, frame.width * fit.scale, frame.height * fit.scale);
    if (mark.state === "box" && mark.box) {
      const origin = normalizedToCss(mark.box.x, mark.box.y, frame.width, frame.height, cssWidth, cssHeight);
      const far = normalizedToCss(mark.box.x + mark.box.w, mark.box.y + mark.box.h, frame.width, frame.height, cssWidth, cssHeight);
      context.strokeStyle = "#e0a100";
      context.lineWidth = 2;
      context.strokeRect(origin.x, origin.y, far.x - origin.x, far.y - origin.y);
    }
  }, [frame, mark]);

  const paintRef = useRef(paint);
  paintRef.current = paint;

  useEffect(() => {
    const image = new Image();
    image.onload = () => {
      imageRef.current = image;
      paintRef.current();
    };
    image.src = `${API_ORIGIN}${frame.url}`;
    return () => {
      image.onload = null;
    };
  }, [frame.url]);

  useEffect(() => {
    paint();
  }, [paint]);

  function point(event: React.PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  return (
    <div className="frame">
      <canvas
        ref={canvasRef}
        aria-label={`Anchor ${frame.frame_id}`}
        onPointerDown={(event) => {
          const canvas = event.currentTarget;
          const local = point(event);
          const normalized = cssToNormalized(local.x, local.y, frame.width, frame.height, canvas.clientWidth, canvas.clientHeight);
          if (!normalized) return;
          drag.current = normalized;
          canvas.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drag.current) return;
          const canvas = event.currentTarget;
          const local = point(event);
          const current = clampToImage(local.x, local.y, frame.width, frame.height, canvas.clientWidth, canvas.clientHeight);
          const box = boxFromPoints(drag.current, current);
          if (box) onChange({ state: "box", box });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      />
      <p>{frame.frame_id} · {formatMs(frame.source_t_ms)} · {mark.state === "unmarked" ? "unmarked" : mark.state === "box" ? "box" : "target not visible"}</p>
      <button type="button" onClick={() => onChange({ state: "not_visible" })}>Target not visible</button>
    </div>
  );
}

function draftFrom(manifest: Manifest | null, revision: Revision | null): Draft {
  if (!manifest) return {};
  const saved = new Map((revision?.anchors ?? []).map((anchor) => [anchor.frame_id, anchor]));
  return Object.fromEntries(
    manifest.frames.map((frame) => {
      const anchor = saved.get(frame.frame_id);
      if (!anchor) return [frame.frame_id, { state: "unmarked" as const }];
      if (anchor.state === "box" && anchor.box) return [frame.frame_id, { state: "box" as const, box: anchor.box }];
      return [frame.frame_id, { state: "not_visible" as const }];
    }),
  );
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
