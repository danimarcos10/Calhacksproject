"use client";

import { useEffect, useRef } from "react";

export type TrackPlayer = { id: number; cls: number; team: number | null; box: number[] };
export type TrackFrame = { t: number; players: TrackPlayer[]; ball: number[] | null };
export type OverlayMoment = { startMs: number; endMs: number; action: string | null; outcome: string | null };
export type OverlayLayers = { rings: boolean; marker: boolean; shadow: boolean; ball: boolean; moments: boolean };
type Box = { x: number; y: number; w: number; h: number };
type Ghost = { wall: number; x: number; y: number; rx: number; ry: number };

const RING = "rgba(255, 255, 255, 0.55)";
const CHOSEN = "#1d5fbf";
const HATCH = "rgba(255, 255, 255, 0.8)";
const BALL = "#ffffff";
const CHIP = "rgba(10, 10, 10, 0.78)";
const SHADOW_MS = 400;
const PASS_MS = 1500;
const ALL: OverlayLayers = { rings: true, marker: true, shadow: true, ball: true, moments: true };

export function VideoOverlay({
  videoRef,
  frames,
  selectedId,
  onPick,
  moments = [],
  layers,
}: {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  frames: TrackFrame[];
  selectedId: number | null;
  onPick?: (box: Box, id: number) => void;
  moments?: OverlayMoment[];
  layers?: Partial<OverlayLayers>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trail = useRef<{ t: number; x: number; y: number }[]>([]);
  const ghosts = useRef<Ghost[]>([]);
  const clock = useRef({ wall: 0, video: 0 });
  const options = useRef({ show: ALL, moments });

  useEffect(() => {
    options.current = { show: { ...ALL, ...layers }, moments };
  });

  useEffect(() => {
    let frame = 0;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const draw = () => {
      frame = requestAnimationFrame(draw);
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || !frames.length) return;
      const { show, moments } = options.current;
      const width = video.clientWidth;
      const height = video.clientHeight;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const now = performance.now();
      const tMs = video.currentTime * 1000;
      const jumped = Math.abs(tMs - clock.current.video - (now - clock.current.wall) * video.playbackRate * (video.paused ? 0 : 1)) > 250;
      clock.current = { wall: now, video: tMs };
      if (jumped) {
        ghosts.current = [];
        trail.current = [];
      }
      const sample = sampleAt(frames, tMs);
      if (!sample) return;
      let chosen: { cx: number; feet: number; top: number; rx: number; ry: number } | null = null;

      for (const player of sample.players) {
        const [x, y, w, h] = player.box;
        const cx = (x + w / 2) * width;
        const feet = (player.id === 0 ? y + h / 2 : y + h) * height;
        if (player.id === selectedId) {
          const rx = Math.max(12, w * width * 0.75);
          chosen = { cx, feet, top: y * height, rx, ry: Math.max(5, rx * 0.32) };
          continue;
        }
        if (!show.rings) continue;
        ctx.beginPath();
        ctx.ellipse(cx, feet, Math.max(8, (w * width) / 2), Math.max(3, w * width * 0.16), 0, 0, Math.PI * 2);
        ctx.strokeStyle = RING;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      if (chosen && show.shadow && !still.matches) {
        const last = ghosts.current[ghosts.current.length - 1];
        if (!last || now - last.wall > 40) ghosts.current.push({ wall: now, x: chosen.cx, y: chosen.feet, rx: chosen.rx, ry: chosen.ry });
        ghosts.current = ghosts.current.filter((ghost) => now - ghost.wall < SHADOW_MS);
        drawShadow(ctx, ghosts.current, now);
      } else {
        ghosts.current = [];
      }

      if (chosen && show.marker) drawMarker(ctx, chosen, height);

      if (show.ball && show.moments) {
        const pass = moments.find((moment) => moment.action === "pass" && tMs >= moment.startMs && tMs <= moment.startMs + PASS_MS);
        if (pass) drawPass(ctx, frames, pass.startMs, tMs, width, height);
      }

      if (show.ball && sample.ball) {
        const [x, y, w, h] = sample.ball;
        const cx = (x + w / 2) * width;
        const cy = (y + h / 2) * height;
        if (!still.matches) {
          const lastBall = trail.current[trail.current.length - 1];
          if (!lastBall || tMs - lastBall.t > 80) trail.current.push({ t: tMs, x: cx, y: cy });
          trail.current = trail.current.filter((point) => tMs - point.t < 700 && point.t <= tMs).slice(-6);
          trail.current.forEach((point, index) => {
            ctx.beginPath();
            ctx.arc(point.x, point.y, 2 + index * 0.6, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(255, 255, 255, ${0.2 + index * 0.08})`;
            ctx.fill();
          });
        }
        ctx.beginPath();
        ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = BALL;
        ctx.fill();
      }

      if (chosen && show.marker) {
        const live = show.moments ? moments.find((moment) => tMs >= moment.startMs && tMs <= moment.endMs) : undefined;
        const text = live ? chipText(live) : selectedId && selectedId > 0 ? `#${selectedId}` : "";
        if (text) drawChip(ctx, text, chosen.cx, chosen.top - 10, width);
      }
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [frames, selectedId, videoRef]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !onPick) return;
    const onClick = (event: MouseEvent) => {
      const rect = video.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width;
      const y = (event.clientY - rect.top) / rect.height;
      if (y > 0.9) return;
      event.preventDefault();
      event.stopPropagation();
      const sample = frames.length ? sampleAt(frames, video.currentTime * 1000) : null;
      const hit = sample?.players
        .filter((player) => player.cls !== 3 && player.id > 0)
        .map((player) => {
          const [px, py, pw, ph] = player.box;
          const pad = Math.max(0.02, ph * 0.35);
          const inside = x >= px - pad && x <= px + pw + pad && y >= py - pad && y <= py + ph + pad;
          const dx = x - (px + pw / 2);
          const dy = y - (py + ph / 2);
          return { player, inside, distance: dx * dx + dy * dy };
        })
        .filter((item) => item.inside)
        .sort((a, b) => a.distance - b.distance)[0]?.player;
      if (hit) {
        const [px, py, pw, ph] = hit.box;
        onPick({ x: px, y: py, w: pw, h: ph }, hit.id);
      }
    };
    video.addEventListener("click", onClick, true);
    return () => video.removeEventListener("click", onClick, true);
  }, [frames, onPick, videoRef]);

  return <canvas ref={canvasRef} className="overlay" />;
}

function drawShadow(ctx: CanvasRenderingContext2D, ghosts: Ghost[], now: number) {
  for (let index = 0; index < ghosts.length - 1; index += 1) {
    const ghost = ghosts[index];
    const life = 1 - (now - ghost.wall) / SHADOW_MS;
    if (life <= 0) continue;
    ctx.beginPath();
    ctx.ellipse(ghost.x, ghost.y, ghost.rx * (0.7 + 0.3 * life), ghost.ry * (0.7 + 0.3 * life), 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(29, 95, 191, ${(0.3 * life).toFixed(3)})`;
    ctx.fill();
  }
  if (ghosts.length > 1) {
    ctx.beginPath();
    ghosts.forEach((ghost, index) => (index ? ctx.lineTo(ghost.x, ghost.y) : ctx.moveTo(ghost.x, ghost.y)));
    ctx.strokeStyle = "rgba(29, 95, 191, 0.35)";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.stroke();
  }
}

function drawMarker(ctx: CanvasRenderingContext2D, at: { cx: number; feet: number; top: number; rx: number; ry: number }, height: number) {
  const { cx, feet, top, rx, ry } = at;
  const crown = Math.max(0, top - (feet - top) * 0.35);
  const beam = ctx.createLinearGradient(0, feet, 0, crown);
  beam.addColorStop(0, "rgba(255, 255, 255, 0.22)");
  beam.addColorStop(1, "rgba(255, 255, 255, 0)");
  ctx.beginPath();
  ctx.moveTo(cx - rx, feet);
  ctx.lineTo(cx - rx * 0.55, Math.min(crown, height));
  ctx.lineTo(cx + rx * 0.55, Math.min(crown, height));
  ctx.lineTo(cx + rx, feet);
  ctx.closePath();
  ctx.fillStyle = beam;
  ctx.fill();

  ctx.save();
  ctx.beginPath();
  ctx.ellipse(cx, feet, rx, ry, 0, 0, Math.PI * 2);
  ctx.clip();
  ctx.strokeStyle = HATCH;
  ctx.lineWidth = 1.25;
  for (let offset = -rx * 2; offset < rx * 2; offset += 5) {
    ctx.beginPath();
    ctx.moveTo(cx + offset - ry, feet + ry);
    ctx.lineTo(cx + offset + ry, feet - ry);
    ctx.stroke();
  }
  ctx.restore();

  ctx.beginPath();
  ctx.ellipse(cx, feet, rx, ry, 0, 0, Math.PI * 2);
  ctx.strokeStyle = CHOSEN;
  ctx.lineWidth = 2.5;
  ctx.stroke();
  ctx.beginPath();
  ctx.ellipse(cx, feet, rx + 4, ry + 2, 0, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.7)";
  ctx.lineWidth = 1;
  ctx.stroke();
}

function drawPass(ctx: CanvasRenderingContext2D, frames: TrackFrame[], startMs: number, tMs: number, width: number, height: number) {
  const path = frames
    .filter((frame) => frame.ball && frame.t >= startMs && frame.t <= Math.min(tMs, startMs + PASS_MS - 300))
    .map((frame) => {
      const [x, y, w, h] = frame.ball!;
      return { x: (x + w / 2) * width, y: (y + h / 2) * height };
    });
  if (path.length < 2) return;
  const fade = Math.min(1, (startMs + PASS_MS - tMs) / 300);
  ctx.save();
  ctx.globalAlpha = Math.max(0, fade);
  ctx.beginPath();
  ctx.moveTo(path[0].x, path[0].y);
  for (let index = 1; index < path.length - 1; index += 1) {
    const mid = { x: (path[index].x + path[index + 1].x) / 2, y: (path[index].y + path[index + 1].y) / 2 };
    ctx.quadraticCurveTo(path[index].x, path[index].y, mid.x, mid.y);
  }
  const end = path[path.length - 1];
  const before = path[path.length - 2];
  ctx.lineTo(end.x, end.y);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.stroke();
  const angle = Math.atan2(end.y - before.y, end.x - before.x);
  ctx.beginPath();
  ctx.moveTo(end.x + Math.cos(angle) * 4, end.y + Math.sin(angle) * 4);
  ctx.lineTo(end.x + Math.cos(angle + 2.6) * 11, end.y + Math.sin(angle + 2.6) * 11);
  ctx.lineTo(end.x + Math.cos(angle - 2.6) * 11, end.y + Math.sin(angle - 2.6) * 11);
  ctx.closePath();
  ctx.fillStyle = CHOSEN;
  ctx.fill();
  ctx.restore();
}

function drawChip(ctx: CanvasRenderingContext2D, text: string, cx: number, bottom: number, width: number) {
  ctx.font = "500 12px Geist, system-ui, sans-serif";
  const textWidth = ctx.measureText(text).width;
  const chipWidth = textWidth + 16;
  const x = Math.min(Math.max(4, cx - chipWidth / 2), width - chipWidth - 4);
  const y = Math.max(4, bottom - 22);
  ctx.beginPath();
  ctx.roundRect(x, y, chipWidth, 22, 11);
  ctx.fillStyle = CHIP;
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + 8, y + 11.5);
  ctx.textBaseline = "alphabetic";
}

function chipText(moment: OverlayMoment) {
  const action = (moment.action ?? "action").replaceAll("_", " ");
  const outcome = moment.outcome?.replaceAll("_", " ");
  return outcome ? `${action.charAt(0).toUpperCase()}${action.slice(1)} · ${outcome}` : `${action.charAt(0).toUpperCase()}${action.slice(1)}`;
}

export function pathFrames(marks: { t: number; box: Box }[]): TrackFrame[] {
  const ordered = [...marks].sort((left, right) => left.t - right.t);
  const player = (box: Box): TrackPlayer => ({ id: 0, cls: 2, team: null, box: [box.x, box.y, box.w, box.h] });
  if (ordered.length <= 1) {
    const only = ordered[0];
    return only ? [{ t: only.t, players: [player(only.box)], ball: null }] : [];
  }
  const frames: TrackFrame[] = [];
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const from = ordered[index];
    const to = ordered[index + 1];
    const steps = Math.max(1, Math.round((to.t - from.t) / 100));
    for (let step = 0; step < steps; step += 1) {
      const alpha = step / steps;
      frames.push({
        t: Math.round(from.t + (to.t - from.t) * alpha),
        players: [
          player({
            x: from.box.x + (to.box.x - from.box.x) * alpha,
            y: from.box.y + (to.box.y - from.box.y) * alpha,
            w: from.box.w + (to.box.w - from.box.w) * alpha,
            h: from.box.h + (to.box.h - from.box.h) * alpha,
          }),
        ],
        ball: null,
      });
    }
  }
  const last = ordered[ordered.length - 1];
  frames.push({ t: last.t, players: [player(last.box)], ball: null });
  return frames;
}

export function trackAtClick(frames: TrackFrame[], tMs: number, box: Box): number | null {
  const sample = sampleAt(frames, tMs);
  if (!sample) return null;
  let best: TrackPlayer | null = null;
  let bestScore = 0;
  for (const player of sample.players) {
    if (player.cls === 3) continue;
    const [x, y, w, h] = player.box;
    const ix = Math.max(0, Math.min(x + w, box.x + box.w) - Math.max(x, box.x));
    const iy = Math.max(0, Math.min(y + h, box.y + box.h) - Math.max(y, box.y));
    const score = (ix * iy) / Math.max(w * h, 0.0001);
    if (score > bestScore) {
      best = player;
      bestScore = score;
    }
  }
  return best && bestScore > 0.05 ? best.id : null;
}

export function sampleAt(frames: TrackFrame[], tMs: number): TrackFrame | null {
  if (!frames.length) return null;
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (frames[mid].t < tMs) lo = mid + 1;
    else hi = mid;
  }
  const next = frames[lo];
  const prev = frames[Math.max(0, lo - 1)];
  if (prev === next || next.t === prev.t) return prev;
  const span = next.t - prev.t;
  if (span > 400) return Math.abs(prev.t - tMs) <= Math.abs(next.t - tMs) ? prev : next;
  const alpha = Math.min(1, Math.max(0, (tMs - prev.t) / span));
  const players = prev.players.flatMap((player) => {
    const other = next.players.find((item) => item.id === player.id);
    if (!other) return alpha < 0.5 ? [player] : [];
    return [{ ...player, box: player.box.map((value, index) => value + (other.box[index] - value) * alpha) }];
  });
  for (const player of next.players) {
    if (!players.some((item) => item.id === player.id) && alpha >= 0.5) players.push(player);
  }
  let ball: number[] | null = null;
  if (prev.ball && next.ball) ball = prev.ball.map((value, index) => value + (next.ball![index] - value) * alpha);
  else ball = alpha < 0.5 ? prev.ball : next.ball;
  return { t: tMs, players, ball };
}
