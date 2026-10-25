"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_ORIGIN, ApiError, getVideo, startScoutBatch, uploadClip } from "@/lib/api";
import { rememberCode } from "@/lib/reviewAccess";
import { ClipWell } from "@/components/ClipWell";
import { useCue, useWorking } from "@/components/Look";
import { useScreenScope } from "@/components/Shell";
import { VideoOverlay, type TrackFrame } from "@/components/VideoOverlay";

type Box = { x: number; y: number; w: number; h: number };
type Tracking = { state: string; done: number; total: number };

type Clip = {
  localId: string;
  file: File;
  videoId: string;
  upload: number | null;
  tracking: Tracking;
  frames: TrackFrame[];
  framesLoaded: boolean;
  held: TrackFrame[] | null;
  marks: { t: number; box: Box }[];
  box: Box | null;
  selectedId: number | null;
  pickedAt: number | null;
  skipped: boolean;
};

const MAX_CLIPS = 6;
const WAITING: Tracking = { state: "waiting", done: 0, total: 0 };

export function ScoutStart() {
  useScreenScope("No submission open");
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [activeId, setActiveId] = useState("");
  const [rights, setRights] = useState("I have the rights to analyse this footage.");
  const [name, setName] = useState("");
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const cue = useCue();
  const active = clips.find((clip) => clip.localId === activeId) ?? clips[0];
  const pending = clips.some((clip) => clip.videoId && clip.tracking.state !== "succeeded" && clip.tracking.state !== "failed");
  useWorking(busy !== "" || clips.some((clip) => clip.upload != null || clip.tracking.state === "queued" || clip.tracking.state === "running"));
  const tracked = useRef<Record<string, string>>({});

  useEffect(() => {
    for (const clip of clips) {
      const before = tracked.current[clip.localId];
      if (before && before !== "succeeded" && clip.tracking.state === "succeeded") cue("meet");
      tracked.current[clip.localId] = clip.tracking.state;
    }
  }, [clips, cue]);

  useEffect(() => {
    if (!pending) return;
    let stop = false;
    const poll = async () => {
      const current = clips.filter((clip) => clip.videoId && clip.tracking.state !== "succeeded" && clip.tracking.state !== "failed");
      await Promise.all(
        current.map(async (clip) => {
          try {
            const video = await getVideo(clip.videoId);
            if (stop) return;
            const tracking = video.tracking ?? WAITING;
            setClips((rows) => {
              let changed = false;
              const next = rows.map((item) => {
                if (item.localId !== clip.localId) return item;
                if (item.tracking.state === tracking.state && item.tracking.done === tracking.done && item.tracking.total === tracking.total) return item;
                changed = true;
                return { ...item, tracking };
              });
              return changed ? next : rows;
            });
          } catch {
            if (!stop) setMessage("The tracking status could not be read.");
          }
        }),
      );
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [clips, pending]);

  useEffect(() => {
    const ready = clips.filter((clip) => clip.videoId && clip.tracking.state === "succeeded" && !clip.framesLoaded);
    if (!ready.length) return;
    let stop = false;
    for (const clip of ready) {
      fetch(`${API_ORIGIN}/api/videos/${clip.videoId}/tracks`)
        .then((response) => response.json())
        .then((body) => {
          if (stop) return;
          setClips((rows) => rows.map((item) => (item.localId === clip.localId && !item.framesLoaded ? { ...item, frames: body.frames ?? [], framesLoaded: true } : item)));
        })
        .catch(() => {
          if (!stop) {
            setMessage("The tracking overlay could not be loaded.");
            setClips((rows) => rows.map((item) => (item.localId === clip.localId ? { ...item, framesLoaded: true } : item)));
          }
        });
    }
    return () => {
      stop = true;
    };
  }, [clips]);

  function addFiles(list: FileList | null) {
    if (!list?.length) return;
    const room = MAX_CLIPS - clips.length;
    const chosen = [...list].slice(0, Math.max(0, room));
    if (list.length > chosen.length) setMessage(`Only ${MAX_CLIPS} clips can be analysed together.`);
    else setMessage("");
    const next = chosen.map((file) => ({
      localId: crypto.randomUUID(),
      file,
      videoId: "",
      upload: null,
      tracking: WAITING,
      frames: [],
      framesLoaded: false,
      held: null,
      marks: [],
      box: null,
      selectedId: null,
      pickedAt: null,
      skipped: false,
    }));
    setClips((rows) => [...rows, ...next]);
    if (!activeId && next[0]) setActiveId(next[0].localId);
  }

  function patch(localId: string, update: Partial<Clip>) {
    setClips((rows) => rows.map((item) => (item.localId === localId ? { ...item, ...update } : item)));
  }

  async function upload() {
    if (!rights.trim()) return;
    setBusy("Uploading");
    setMessage("");
    try {
      for (const clip of clips) {
        if (clip.videoId) continue;
        const video = await uploadClip(clip.file, rights, (fraction) => patch(clip.localId, { upload: fraction }));
        patch(clip.localId, { videoId: video.id, upload: null, tracking: video.tracking ?? { state: "running", done: 0, total: 0 } });
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The upload failed.");
    } finally {
      setBusy("");
    }
  }

  async function analyse() {
    const chosen = clips.filter((clip) => clip.box && clip.selectedId && !clip.skipped && clip.videoId && clip.tracking.state === "succeeded");
    if (!name.trim() || chosen.length === 0) return;
    setBusy("Opening the review");
    setMessage("");
    try {
      const started = await startScoutBatch({
        player_name: name.trim(),
        clips: chosen.map((clip) => ({ video_id: clip.videoId, t_ms: clip.pickedAt ?? 0, box: clip.box! })),
      });
      rememberCode(started.key, started.code);
      router.push(`/review/${started.key}?code=${encodeURIComponent(started.code)}`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The analysis could not start.");
      setBusy("");
    }
  }

  const uploaded = clips.length > 0 && clips.every((clip) => clip.videoId);
  const readyCount = clips.filter((clip) => clip.box && clip.selectedId && !clip.skipped).length;
  const showVideo = active && active.tracking.state === "succeeded" && !active.skipped;

  return (
    <main className="screen scout-start">
      <header className="title-row">
        <div>
          <h1>Scout</h1>
          <p className="sub">
            {clips.length === 0
              ? "Choose up to 6 short clips of the same player."
              : showVideo
                ? active.selectedId
                  ? `Player #${active.selectedId} highlighted. Every other ring stays on its player, and the ball stays marked.`
                  : "Every player has a ring, and the ball is marked. Click the player to follow."
                : "Each clip is tracked, then you click the player once."}
          </p>
        </div>
      </header>
      <div className="split">
        <div className="stage-well">
          {clips.length === 0 && (
            <label className="drop">
              <ClipWell />
              <span className="drop-title">Choose match clips</span>
              <span className="meta">MP4 or MOV. Up to {MAX_CLIPS} clips.</span>
              <input type="file" accept="video/mp4,video/quicktime" multiple onChange={(event) => addFiles(event.target.files)} />
            </label>
          )}
          {active && !showVideo && (
            <div className="drop">
              <ClipWell at={active.upload ?? (active.tracking.total ? active.tracking.done / active.tracking.total : undefined)} />
              <p>{clipStatus(active)}</p>
              {active.videoId && active.tracking.state !== "failed" && active.tracking.state !== "waiting" && (
                <div className="meter" role="progressbar" aria-valuenow={active.tracking.done} aria-valuemax={active.tracking.total || undefined} aria-label="Player tracking" style={{ width: "70%" }}>
                  <span style={{ transform: `scaleX(${active.tracking.total ? Math.min(1, active.tracking.done / active.tracking.total) : 0})` }} />
                </div>
              )}
            </div>
          )}
          {showVideo && active && (
            <div className="stage-frame">
              <video
                key={active.videoId}
                ref={videoRef}
                src={`${API_ORIGIN}/api/videos/${active.videoId}/media`}
                controls
                playsInline
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
              />
              <VideoOverlay
                videoRef={videoRef}
                frames={active.frames}
                selectedId={active.selectedId}
                onPick={(next, id) => {
                  if (!id) return;
                  const player = videoRef.current;
                  patch(active.localId, {
                    box: next,
                    selectedId: id,
                    pickedAt: player ? Math.round(player.currentTime * 1000) : 0,
                    skipped: false,
                  });
                }}
              />
            </div>
          )}
        </div>
        <div className="side-form">
          {!uploaded && (
            <>
              <label>
                Rights
                <input type="text" value={rights} onChange={(event) => setRights(event.target.value)} />
              </label>
              {clips.length > 0 && clips.length < MAX_CLIPS && (
                <label className="link-file">
                  Add another clip
                  <input type="file" accept="video/mp4,video/quicktime" multiple onChange={(event) => addFiles(event.target.files)} />
                </label>
              )}
              <button type="button" className="primary" disabled={clips.length === 0 || !rights.trim() || busy !== ""} onClick={() => void upload()}>
                {busy === "Uploading" ? "Uploading" : clips.length === 0 ? "Upload" : `Upload ${clips.length} ${clips.length === 1 ? "clip" : "clips"}`}
              </button>
            </>
          )}
          {clips.length > 0 && (
            <div className="clip-list">
              {clips.map((clip, index) => (
                <button key={clip.localId} type="button" aria-pressed={clip.localId === active?.localId} onClick={() => setActiveId(clip.localId)}>
                  <span>Clip {index + 1}</span>
                  <span className="meta">{clip.file.name}</span>
                  <span className="meta">{clip.skipped ? "Not in this clip" : clip.selectedId ? `Player #${clip.selectedId}` : clipStatus(clip)}</span>
                </button>
              ))}
            </div>
          )}
          {uploaded && (
            <>
              {showVideo && (
                <button
                  type="button"
                  onClick={() => {
                    const player = videoRef.current;
                    if (!player) return;
                    if (player.paused) void player.play();
                    else player.pause();
                  }}
                >
                  {playing ? "Pause" : "Play"}
                </button>
              )}
              {active && active.tracking.state === "succeeded" && (
                <button type="button" onClick={() => patch(active.localId, { skipped: !active.skipped, box: active.skipped ? active.box : null, selectedId: active.skipped ? active.selectedId : null })}>
                  {active.skipped ? "Player is in this clip" : "Not in this clip"}
                </button>
              )}
              <label>
                Name
                <input type="text" value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <button type="button" className="primary" disabled={readyCount === 0 || !name.trim() || busy !== "" || pending} onClick={() => void analyse()}>
                {busy === "Opening the review" ? "Opening" : `Analyse ${readyCount} ${readyCount === 1 ? "clip" : "clips"}`}
              </button>
            </>
          )}
          {message && <p className="error">{message}</p>}
        </div>
      </div>
    </main>
  );
}

function clipStatus(clip: Clip) {
  if (!clip.videoId) return clip.upload != null ? `Uploading ${Math.round(clip.upload * 100)}%` : "Waiting to upload";
  if (clip.tracking.state === "queued") return "Waiting to track";
  if (clip.tracking.state === "failed") return "Tracking failed";
  if (clip.tracking.state === "succeeded") return "Click the player";
  const total = clip.tracking.total || 0;
  return `Tracking ${clip.tracking.done} / ${total || "?"} frames`;
}
