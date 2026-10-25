"use client";

import { useCallback, useEffect, useRef } from "react";
import { API_ORIGIN, type Anchor, type Frame, type Manifest, type Revision, formatMs } from "@/lib/api";
import { boxFromPoints, clampToImage, containFit, cssToNormalized, normalizedToCss, type Box } from "@/lib/geometry";

export type Mark = {
  state: "unmarked" | "located" | "not_visible" | "uncertain";
  source?: "manual" | "estimated";
  box?: Box;
  method?: string;
  reason?: string;
};
export type Draft = Record<string, Mark>;

export const CONFIRMED_ESTIMATE = "confirmed_estimate";

export function AnchorCard({
  frame,
  mark,
  attention,
  onChange,
}: {
  frame: Frame;
  mark: Mark;
  attention: boolean;
  onChange: (next: Mark) => void;
}) {
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
    if ((mark.state === "located" || mark.state === "uncertain") && mark.box) {
      const origin = normalizedToCss(mark.box.x, mark.box.y, frame.width, frame.height, cssWidth, cssHeight);
      const far = normalizedToCss(mark.box.x + mark.box.w, mark.box.y + mark.box.h, frame.width, frame.height, cssWidth, cssHeight);
      context.strokeStyle = mark.state === "uncertain" ? "#dc3c3c" : mark.source === "estimated" ? "#00c4d2" : "#e0a100";
      context.lineWidth = 2;
      context.setLineDash(mark.source === "estimated" ? [6, 4] : []);
      context.strokeRect(origin.x, origin.y, far.x - origin.x, far.y - origin.y);
      context.setLineDash([]);
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
    <div className={attention ? "frame attention" : "frame"} id={`frame-${frame.frame_id}`}>
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
          if (box) onChange({ state: "located", source: "manual", box });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      />
      <p>
        {frame.frame_id} · {formatMs(frame.source_t_ms)} · <span className={chipClass(mark)}>{chipText(mark)}</span>
      </p>
      <div className="actions">
        {mark.state === "located" && mark.source === "estimated" && (
          <button type="button" onClick={() => onChange({ ...mark, source: "manual", method: CONFIRMED_ESTIMATE })}>
            Confirm box
          </button>
        )}
        <button type="button" onClick={() => onChange({ state: "not_visible", reason: "Marked not visible on this frame." })}>Not visible</button>
        <button type="button" onClick={() => onChange({ state: "uncertain", source: "manual", box: mark.box, reason: "Location needs a check." })}>Uncertain</button>
        <button type="button" onClick={() => onChange({ state: "unmarked" })}>Clear</button>
      </div>
    </div>
  );
}

export function draftFrom(manifest: Manifest | null, revision: Revision | null): Draft {
  if (!manifest) return {};
  const saved = new Map((revision?.anchors ?? []).map((anchor) => [anchor.frame_id, anchor]));
  return Object.fromEntries(
    manifest.frames.map((frame) => {
      const anchor = saved.get(frame.frame_id);
      if (!anchor) return [frame.frame_id, { state: "unmarked" as const }];
      if (anchor.state === "located" && anchor.box) {
        return [frame.frame_id, { state: "located" as const, source: anchor.source === "estimated" ? "estimated" as const : "manual" as const, box: anchor.box, method: anchor.method ?? undefined, reason: anchor.reason ?? undefined }];
      }
      if (anchor.state === "uncertain") {
        return [frame.frame_id, { state: "uncertain" as const, source: anchor.source === "estimated" ? "estimated" as const : "manual" as const, box: anchor.box ?? undefined, reason: anchor.reason ?? undefined }];
      }
      if (anchor.state === "not_visible") return [frame.frame_id, { state: "not_visible" as const, reason: anchor.reason ?? undefined }];
      return [frame.frame_id, { state: "unmarked" as const }];
    }),
  );
}

export function anchorFrom(frameId: string, mark: Mark | undefined): Anchor | null {
  if (!mark || mark.state === "unmarked") return null;
  if (mark.state === "located" && mark.box) {
    return {
      frame_id: frameId,
      state: "located",
      source: mark.source ?? "manual",
      box: mark.box,
      method: mark.method ?? null,
      reason: mark.reason ?? null,
      explicit: false,
    };
  }
  if (mark.state === "uncertain") {
    return {
      frame_id: frameId,
      state: "uncertain",
      source: mark.source ?? "manual",
      box: mark.box ?? null,
      method: mark.method ?? null,
      reason: mark.reason ?? "Location needs a check.",
      explicit: true,
    };
  }
  return {
    frame_id: frameId,
    state: "not_visible",
    source: null,
    box: null,
    method: null,
    reason: mark.reason ?? "Marked not visible on this frame.",
    explicit: true,
  };
}

export function chipText(mark: Mark) {
  if (mark.state === "located" && mark.source === "estimated") return "estimated";
  if (mark.state === "located" && mark.method === CONFIRMED_ESTIMATE) return "confirmed estimate";
  if (mark.state === "located") return "manual";
  if (mark.state === "not_visible") return "not visible";
  if (mark.state === "uncertain") return "uncertain";
  return "not annotated";
}

export function chipClass(mark: Mark) {
  if (mark.state === "located" && mark.source === "estimated") return "chip estimated";
  if (mark.state === "located") return "chip manual";
  if (mark.state === "not_visible") return "chip hidden";
  if (mark.state === "uncertain") return "chip uncertain";
  return "chip unmarked";
}
