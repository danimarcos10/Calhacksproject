"use client";

import Link from "next/link";
import { useMutation, useQuery } from "convex/react";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../convex/_generated/api";
import type { Doc } from "../../convex/_generated/dataModel";
import { AnchorCard, CONFIRMED_ESTIMATE, anchorFrom, draftFrom, type Draft, type Mark } from "@/components/AnchorEditor";
import { type Anchor, type Revision, type VideoDetail, formatMs, getVideo, proposeLocations } from "@/lib/api";
import { codeFor, errorText, reviewerName } from "@/lib/reviewAccess";

type ConvexAnchor = Doc<"revisions">["anchors"][number];

function toConvex(anchor: Anchor): ConvexAnchor {
  const out: ConvexAnchor = { frameId: anchor.frame_id, state: anchor.state };
  if (anchor.source) out.source = anchor.source;
  if (anchor.box) out.box = anchor.box;
  if (anchor.method) out.method = anchor.method;
  if (anchor.reason) out.reason = anchor.reason;
  if (anchor.explicit) out.explicit = true;
  return out;
}

function toSnake(anchor: ConvexAnchor): Anchor {
  return {
    frame_id: anchor.frameId,
    state: anchor.state,
    source: anchor.source ?? null,
    box: anchor.box ?? null,
    method: anchor.method ?? null,
    reason: anchor.reason ?? null,
    explicit: anchor.explicit ?? false,
  };
}

const CARRY_GAP_MS = 600;

// A box is carried into the next window only when both windows come from the same
// clip, touch end to start, and the box sits on a frame next to the boundary.
// Anything further away could cross a cut or a pan, so the coach marks it fresh.
function carryCandidate(
  previous: { videoKey: string; endMs: number; frames: { frameId: string; tMs: number }[]; revision: { anchors: ConvexAnchor[] } | null } | null,
  videoKey: string,
  startMs: number,
): ConvexAnchor | null {
  if (!previous || previous.videoKey !== videoKey || previous.endMs !== startMs || !previous.revision) return null;
  const times = new Map(previous.frames.map((f) => [f.frameId, f.tMs]));
  const last = [...previous.revision.anchors]
    .filter((a) => a.state === "located" && a.box)
    .sort((a, b) => (times.get(a.frameId) ?? 0) - (times.get(b.frameId) ?? 0))
    .pop();
  if (!last || startMs - (times.get(last.frameId) ?? -Infinity) > CARRY_GAP_MS) return null;
  return last;
}

export function PrepareWindowRoute() {
  const { id, window } = useParams<{ id: string; window: string }>();
  return <PrepareWindow submissionKey={id} order={Number(window)} />;
}

export function PrepareWindow({ submissionKey, order }: { submissionKey: string; order: number }) {
  const params = useSearchParams();
  const mode = params.get("mode") === "correction" ? "correction" : "prepare";
  const [code, setCode] = useState<string | null | undefined>(undefined);
  useEffect(() => setCode(codeFor(submissionKey)), [submissionKey]);
  const review = useQuery(api.review.get, code ? { key: submissionKey, code } : "skip");
  const saveRevision = useMutation(api.review.saveRevision);
  const queueAnalysis = useMutation(api.review.queueAnalysis);

  const window = review?.windows.find((w) => w.order === order) ?? null;
  const previous = review?.windows.find((w) => w.order === order - 1) ?? null;
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [base, setBase] = useState<number | null>(null);
  const [edited, setEdited] = useState<string[]>([]);
  const [jersey, setJersey] = useState("");
  const [teamColor, setTeamColor] = useState("");
  const [offered, setOffered] = useState(0);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [savedNumber, setSavedNumber] = useState<number | null>(null);

  useEffect(() => {
    if (!window) return;
    getVideo(window.videoKey).then(setVideo).catch((error: Error) => setMessage(error.message));
  }, [window?.videoKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const manifest = useMemo(() => video?.manifests.find((m) => m.id === window?.manifestKey) ?? null, [video, window?.manifestKey]);

  function loadSaved() {
    if (!manifest || !window) return;
    setDraft(draftFrom(manifest, { anchors: (window.revision?.anchors ?? []).map(toSnake) } as Revision));
    setBase(window.currentRevision);
    setEdited([]);
    setJersey(window.revision?.jerseyNote ?? "");
    setTeamColor(window.revision?.teamColorNote ?? "");
    setOffered(0);
  }

  useEffect(() => {
    if (base === null || edited.length === 0) loadSaved();
    // Reload only when the saved selection changes and nothing is being edited.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest, window?.currentRevision]);

  if (code === undefined) return <main className="app"><p className="meta">Opening…</p></main>;
  if (!code) {
    return (
      <main className="app">
        <p className="error">Open the review link for this submission first, so this browser has its review code.</p>
        <Link href="/review">Review inbox</Link>
      </main>
    );
  }
  if (!review || !window) return <main className="app"><p className="meta">Loading the window…</p></main>;

  const conflict = base !== null && window.currentRevision !== base;
  const access = { key: submissionKey, code };
  const reviewer = reviewerName();

  function change(frameId: string, next: Mark) {
    setDraft((current) => ({ ...current, [frameId]: next }));
    setEdited((current) => (current.includes(frameId) ? current : [...current, frameId]));
    setSavedNumber(null);
  }

  function anchors(): Anchor[] {
    if (!manifest) return [];
    return manifest.frames.flatMap((frame) => {
      const anchor = anchorFrom(frame.frame_id, draft[frame.frame_id]);
      return anchor ? [anchor] : [];
    });
  }

  async function onPropose() {
    if (!video || !manifest) return;
    const current = anchors();
    if (!current.some((anchor) => anchor.state === "located" && anchor.source !== "estimated")) {
      setMessage("Draw the player on at least one frame before proposing the rest.");
      return;
    }
    setBusy("Proposing locations");
    setMessage("");
    try {
      const proposed = await proposeLocations(video.id, { manifest_id: manifest.id, anchors: current });
      let added = 0;
      const next = { ...draft };
      const touched: string[] = [];
      for (const anchor of proposed.anchors) {
        const existing = next[anchor.frame_id];
        if (existing && existing.state !== "unmarked" && existing.source !== "estimated") continue;
        next[anchor.frame_id] = {
          state: anchor.state,
          source: "estimated",
          box: anchor.box ?? undefined,
          method: anchor.method ?? undefined,
          reason: anchor.reason ?? undefined,
        };
        touched.push(anchor.frame_id);
        added += 1;
      }
      setDraft(next);
      setEdited((list) => [...new Set([...list, ...touched])]);
      setOffered((count) => count + added);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Locations could not be proposed.");
    } finally {
      setBusy("");
    }
  }

  const carried = carryCandidate(previous, window.videoKey, window.startMs);
  const contiguous = carried ? previous : null;

  function carryOver() {
    if (!contiguous || !manifest || !carried) return;
    const located = carried;
    const first = manifest.frames[0];
    if (!located.box || !first) return;
    change(first.frame_id, {
      state: "located",
      source: "estimated",
      box: located.box,
      method: `carried_from_window_${contiguous.order}`,
      reason: `Last box from window ${contiguous.order} of the same clip, which ends where this window starts. Confirm or redraw it.`,
    });
  }

  async function onSave(thenAnalyse: boolean) {
    if (!window || base === null) return;
    const list = anchors();
    setBusy("Saving selection");
    setMessage("");
    try {
      const kept = list.filter((a) => a.source === "estimated" || a.method === CONFIRMED_ESTIMATE).length;
      const result = await saveRevision({
        ...access,
        windowId: window.id,
        baseRevision: base,
        anchors: list.map(toConvex),
        jerseyNote: jersey,
        teamColorNote: teamColor,
        note: "",
        origin: mode,
        proposed: offered ? { offered, kept: Math.min(kept, offered) } : undefined,
        reviewer,
      });
      setBase(result.number);
      setEdited([]);
      setOffered(0);
      setSavedNumber(result.number);
      if (thenAnalyse) {
        await queueAnalysis({ ...access, windowId: window.id, reviewer });
        setMessage(`Selection ${result.number} saved and window ${window.order} queued for analysis.`);
      } else {
        setMessage(`Selection ${result.number} saved.`);
      }
    } catch (error) {
      setMessage(errorText(error, "The selection was not saved."));
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="app">
      <header>
        <p className="meta">
          <Link href={`/review/${submissionKey}`}>Back to the review</Link>
        </p>
        <h1>
          {mode === "correction" ? "Correct the player" : "Prepare"}: window {window.order} ({formatMs(window.startMs)}–{formatMs(window.endMs)})
        </h1>
        <p>{review.submission.player} · {review.submission.title}</p>
        <p className="meta">Linked to this player by {window.link.assertedBy}: “{window.link.statement}”</p>
      </header>
      {mode === "correction" && (
        <div className="banner" role="note">
          Correction. Saving creates selection {window.currentRevision + 1}. Moments made for selection {window.currentRevision} become stale in every open
          session; they leave the playlist and summary and stay in history. Analyse again afterwards.
        </div>
      )}
      {conflict && (
        <div className="banner" role="alert">
          Selection {window.currentRevision} was saved in another session after you opened selection {base}. Saving now is refused.{" "}
          <button type="button" onClick={loadSaved}>Load selection {window.currentRevision}</button>
        </div>
      )}
      {edited.length > 0 && (
        <div className="banner pending" role="status">
          Unsaved edits on {edited.join(", ")}. The coach view and analysis keep using selection {base || "none"} until you save.
        </div>
      )}
      {message && <p className={message.startsWith("Selection") ? "meta" : "error"}>{message}</p>}
      {!manifest && <p className="meta">Loading frames from the local API…</p>}
      {manifest && (
        <section className="panel">
          <div className="controls">
            <button type="button" onClick={() => void onPropose()} disabled={Boolean(busy)}>Propose locations (tracker)</button>
            {contiguous && (
              <button type="button" onClick={carryOver} disabled={Boolean(busy)}>
                Carry last box from window {contiguous.order}
              </button>
            )}
            <span className="meta">
              Hand-drawn boxes are solid gold; tracker or carried estimates are dashed cyan and stay labelled estimated until you confirm them.
            </span>
          </div>
          <div className="frames">
            {manifest.frames.map((frame) => (
              <AnchorCard
                key={frame.frame_id}
                frame={frame}
                mark={draft[frame.frame_id] ?? { state: "unmarked" }}
                attention={edited.includes(frame.frame_id)}
                onChange={(next) => change(frame.frame_id, next)}
              />
            ))}
          </div>
          <div className="controls">
            <label>
              Jersey or number (optional, not used to identify the player)
              <input type="text" value={jersey} onChange={(event) => { setJersey(event.target.value); setEdited((l) => (l.includes("notes") ? l : [...l, "notes"])); }} />
            </label>
            <label>
              Team colour (optional, not used to identify the player)
              <input type="text" value={teamColor} onChange={(event) => { setTeamColor(event.target.value); setEdited((l) => (l.includes("notes") ? l : [...l, "notes"])); }} />
            </label>
          </div>
          <div className="controls">
            <button type="button" onClick={() => void onSave(false)} disabled={Boolean(busy) || conflict || edited.length === 0}>
              Save selection
            </button>
            <button type="button" className="primary" onClick={() => void onSave(true)} disabled={Boolean(busy) || conflict || edited.length === 0}>
              Save and analyse
            </button>
            {savedNumber !== null && edited.length === 0 && window.requests[0]?.revisionNumber !== savedNumber && (
              <button type="button" onClick={() => void queueAnalysis({ ...access, windowId: window.id, reviewer }).then(() => setMessage(`Selection ${savedNumber} saved and queued.`))}>
                Analyse selection {savedNumber}
              </button>
            )}
            <span className="meta">
              {busy || (window.revision ? `Saved selection ${window.revision.number} by ${window.revision.savedBy}` : "No saved selection yet")}
            </span>
          </div>
        </section>
      )}
    </main>
  );
}
