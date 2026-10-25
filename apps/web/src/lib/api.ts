import type { components } from "./api.generated";

export const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

type Schemas = components["schemas"];

export type Frame = Schemas["FrameOut"];
export type Manifest = Schemas["ManifestOut"];
export type Anchor = Schemas["AnchorIn"];
export type Revision = Schemas["RevisionOut"];
export type VideoDetail = Schemas["VideoOut"];
export type Observation = Schemas["ObservationOut"];
export type Analysis = Schemas["AnalysisOut"];
export type Job = Schemas["JobOut"];
export type ProviderStatus = Schemas["ProviderOut"];

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.user_message || "The request failed.");
  }
  return body as T;
}

export function uploadClip(file: File, rightsNote: string, onProgress: (fraction: number) => void) {
  return new Promise<VideoDetail>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_ORIGIN}/api/videos`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || "{}");
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as VideoDetail);
      else reject(new ApiError(body.user_message || "The upload failed."));
    };
    xhr.onerror = () => reject(new ApiError("The upload failed."));
    const data = new FormData();
    data.append("file", file);
    data.append("rights_note", rightsNote);
    xhr.send(data);
  });
}

export async function getVideo(id: string) {
  return parse<VideoDetail>(await fetch(`${API_ORIGIN}/api/videos/${id}`));
}

export async function sampleWindow(videoId: string, startMs: number, endMs: number) {
  return parse<Manifest>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/samples`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_ms: startMs, end_ms: endMs }),
    }),
  );
}

export async function proposeLocations(videoId: string, body: { manifest_id: string; anchors: Anchor[] }) {
  return parse<{ anchors: Anchor[] }>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/proposals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function saveTarget(videoId: string, body: Schemas["TargetRequest"]) {
  return parse<Revision>(
    await fetch(`${API_ORIGIN}/api/videos/${videoId}/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function startAnalysis(videoId: string, manifestId: string, revisionId: string, idempotencyKey: string) {
  return parse<Job>(
    await fetch(`${API_ORIGIN}/api/analyses`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ video_id: videoId, manifest_id: manifestId, target_revision_id: revisionId }),
    }),
  );
}

export async function getJob(id: string) {
  return parse<Job>(await fetch(`${API_ORIGIN}/api/jobs/${id}`));
}

export async function getReady() {
  const response = await fetch(`${API_ORIGIN}/readyz`);
  return (await response.json()) as Schemas["ReadyOut"];
}

export function formatMs(ms: number) {
  const total = Math.max(0, ms) / 1000;
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}
