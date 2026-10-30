"use client";

import { useEffect, useRef, useState } from "react";
import { API_ORIGIN, ApiError, getVideo, uploadClip } from "@/lib/api";
import { ClipWell } from "@/components/ClipWell";
import { useCue, useWorking } from "@/components/Look";
import { useScreenScope } from "@/components/Shell";
import { PitchMap, VideoOverlay, type TrackFrame } from "@/components/VideoOverlay";

type Tracking = { state: string; done: number; total: number; phase?: string | null };
type TeamStat = { team: number; possession: number; passes: number; pass_completion: number | null; shots: number };
type PlayerStat = { id: number; team: number | null; passes: number; dribbles: number; shots: number; touches: number };
type ClipAnalysis = { teams: TeamStat[]; players: PlayerStat[] };

type Clip = {
  localId: string;
  file: File;
  videoId: string;
  upload: number | null;
  tracking: Tracking;
  frames: TrackFrame[];
  framesLoaded: boolean;
  analysis: ClipAnalysis | null;
  analysisLoaded: boolean;
  selectedId: number | null;
};

const MAX_CLIPS = 6;
const WAITING: Tracking = { state: "waiting", done: 0, total: 0 };
const TEAM_COLOR = ["#FF1493", "#00BFFF"];
const TEAM_NAME = ["Team A", "Team B"];

export function ScoutStart() {
  useScreenScope("Clip analysis");
  const videoRef = useRef<HTMLVideoElement>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [activeId, setActiveId] = useState("");
  const [rights, setRights] = useState("I have the rights to analyse this footage.");
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
            const tracking = (video.tracking ?? WAITING) as Tracking;
            setClips((rows) => {
              let changed = false;
              const next = rows.map((item) => {
                if (item.localId !== clip.localId) return item;
                if (
                  item.tracking.state === tracking.state &&
                  item.tracking.done === tracking.done &&
                  item.tracking.total === tracking.total &&
                  item.tracking.phase === tracking.phase
                ) {
                  return item;
                }
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
    const ready = clips.filter((clip) => clip.videoId && clip.tracking.state === "succeeded" && (!clip.framesLoaded || !clip.analysisLoaded));
    if (!ready.length) return;
    let stop = false;
    for (const clip of ready) {
      if (!clip.framesLoaded) {
        fetch(`${API_ORIGIN}/api/videos/${clip.videoId}/tracks`)
          .then((response) => response.json())
          .then((body) => {
            if (stop) return;
            setClips((rows) =>
              rows.map((item) => (item.localId === clip.localId && !item.framesLoaded ? { ...item, frames: body.frames ?? [], framesLoaded: true } : item)),
            );
          })
          .catch(() => {
            if (!stop) {
              setMessage("The tracking overlay could not be loaded.");
              setClips((rows) => rows.map((item) => (item.localId === clip.localId ? { ...item, framesLoaded: true } : item)));
            }
          });
      }
      if (!clip.analysisLoaded) {
        fetch(`${API_ORIGIN}/api/videos/${clip.videoId}/analysis`)
          .then((response) => response.json())
          .then((body) => {
            if (stop) return;
            const analysis = Array.isArray(body.teams) ? (body as ClipAnalysis) : null;
            setClips((rows) =>
              rows.map((item) => (item.localId === clip.localId && !item.analysisLoaded ? { ...item, analysis, analysisLoaded: true } : item)),
            );
          })
          .catch(() => {
            if (!stop) {
              setMessage("The clip totals could not be loaded.");
              setClips((rows) => rows.map((item) => (item.localId === clip.localId ? { ...item, analysisLoaded: true } : item)));
            }
          });
      }
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
      analysis: null,
      analysisLoaded: false,
      selectedId: null,
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
        patch(clip.localId, { videoId: video.id, upload: null, tracking: (video.tracking ?? { state: "running", done: 0, total: 0 }) as Tracking });
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The upload failed.");
    } finally {
      setBusy("");
    }
  }

  const uploaded = clips.length > 0 && clips.every((clip) => clip.videoId);
  const showVideo = active && active.tracking.state === "succeeded";
  const selected = active?.analysis?.players.find((player) => player.id === active.selectedId) ?? null;

  return (
    <main className="screen scout-start">
      <header className="title-row">
        <div>
          <h1>Scout</h1>
          <p className="sub">
            {clips.length === 0
              ? "Choose a clip. Tracking marks every player and draws the pitch."
              : showVideo
                ? active.selectedId
                  ? `Player #${active.selectedId} is selected. The totals on the right are for this clip.`
                  : "Team totals are on the right. Click a player for their passes, dribbles, shots and touches."
                : "Each clip is tracked on its own. The totals appear when the pitch map does."}
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
            <div className="stage-stack">
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
                  onPick={(_box, id) => {
                    if (!id) return;
                    patch(active.localId, { selectedId: id });
                  }}
                />
              </div>
              <PitchMap videoRef={videoRef} frames={active.frames} selectedId={active.selectedId} />
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
                  <span className="meta">{clip.selectedId ? `Player #${clip.selectedId}` : clipStatus(clip)}</span>
                </button>
              ))}
            </div>
          )}
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
          {showVideo && active?.analysis && <ClipTotals analysis={active.analysis} selected={selected} selectedId={active.selectedId} />}
          {message && <p className="error">{message}</p>}
        </div>
      </div>
    </main>
  );
}

function ClipTotals({
  analysis,
  selected,
  selectedId,
}: {
  analysis: ClipAnalysis;
  selected: PlayerStat | null;
  selectedId: number | null;
}) {
  return (
    <section className="stat-block">
      <h2>Teams</h2>
      <div className="stat-teams">
        {analysis.teams.map((team) => (
          <div key={team.team}>
            <p className="stat-name">
              <i style={{ background: TEAM_COLOR[team.team] ?? "#ffffff" }} />
              {TEAM_NAME[team.team] ?? `Team ${team.team + 1}`}
            </p>
            <Stat label="Possession" value={percent(team.possession)} />
            <Stat label="Passes" value={String(team.passes)} />
            <Stat label="Completion" value={team.pass_completion == null ? "—" : percent(team.pass_completion)} />
            <Stat label="Shots" value={String(team.shots)} />
          </div>
        ))}
      </div>
      <h2>{selectedId ? `Player #${selectedId}` : "Player"}</h2>
      {selected ? (
        <>
          <Stat label="Passes" value={String(selected.passes)} />
          <Stat label="Dribbles" value={String(selected.dribbles)} />
          <Stat label="Shots" value={String(selected.shots)} />
          <Stat label="Touches" value={String(selected.touches)} />
        </>
      ) : (
        <p className="meta">Click a player on the clip.</p>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <p className="stat-row">
      <span>{label}</span>
      <span>{value}</span>
    </p>
  );
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function clipStatus(clip: Clip) {
  if (!clip.videoId) return clip.upload != null ? `Uploading ${Math.round(clip.upload * 100)}%` : "Waiting to upload";
  if (clip.tracking.state === "queued") return "Waiting to track";
  if (clip.tracking.state === "failed") return "Tracking failed";
  if (clip.tracking.state === "succeeded") return "Tracked";
  if (clip.tracking.phase === "teams") return "Sorting the two teams";
  const total = clip.tracking.total || 0;
  return `Tracking ${clip.tracking.done} / ${total || "?"} frames`;
}
