// Review codes open one submission each. This browser remembers the codes it has
// been given so the inbox can list those submissions. There are no accounts yet;
// the reviewer name is a display name only.

const CODES = "secondlook.reviewCodes";
const NAME = "secondlook.reviewerName";

type Codes = Record<string, string>;

function read(): Codes {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(CODES) ?? "{}") as Codes;
  } catch {
    return {};
  }
}

export function rememberCode(key: string, code: string) {
  window.localStorage.setItem(CODES, JSON.stringify({ ...read(), [key]: code.trim() }));
}

export function forgetCode(key: string) {
  const next = read();
  delete next[key];
  window.localStorage.setItem(CODES, JSON.stringify(next));
}

export function codeFor(key: string): string | null {
  return read()[key] ?? null;
}

export function knownEntries(): { key: string; code: string }[] {
  return Object.entries(read()).map(([key, code]) => ({ key, code }));
}

export function reviewerName(): string {
  if (typeof window === "undefined") return "Coach";
  return window.localStorage.getItem(NAME) || "Coach";
}

export function setReviewerName(name: string) {
  window.localStorage.setItem(NAME, name);
}

export function errorText(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "data" in error) {
    const data = (error as { data: unknown }).data;
    if (data && typeof data === "object" && "message" in data) return String((data as { message: unknown }).message);
  }
  return fallback;
}

export function parseReviewLink(text: string): { key: string; code: string } | null {
  const trimmed = text.trim();
  const match = trimmed.match(/(sub_[0-9a-f]+)\?code=([A-Za-z0-9_-]+)/);
  if (match) return { key: match[1], code: match[2] };
  return null;
}
