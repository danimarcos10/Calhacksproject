"use client";

import Link from "next/link";
import { useQuery } from "convex/react";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { api } from "../../convex/_generated/api";
import { DecisionBar } from "@/components/Charts";
import { ClipWell } from "@/components/ClipWell";
import { useScreenScope } from "@/components/Shell";
import { knownEntries, parseReviewLink, rememberCode } from "@/lib/reviewAccess";

function subscribeInbox(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function inboxEntries() {
  return JSON.stringify(knownEntries());
}

export function ReviewInbox() {
  useScreenScope("No submission open");
  const router = useRouter();
  const stored = useSyncExternalStore(subscribeInbox, inboxEntries, () => "[]");
  const entries = JSON.parse(stored) as { key: string; code: string }[];
  const [link, setLink] = useState("");
  const [message, setMessage] = useState("");
  const rows = useQuery(api.review.inbox, entries.length ? { entries } : "skip");

  return (
    <main className="screen">
      <header className="title-row">
        <div>
          <h1>Review inbox</h1>
          <p className="sub">Player submissions this browser has a review link for. Open one to watch its moments and record decisions.</p>
        </div>
      </header>
      <div className={entries.length === 0 ? "sheet sheet-empty" : "sheet"}>
      {entries.length === 0 && <ClipWell />}
      {entries.length === 0 && <p className="sub sheet-copy">No submission yet. Paste a review link below.</p>}
      {rows === undefined && entries.length > 0 && <div className="skeleton skel-block" />}
      {rows && rows.length > 0 && (
        <ul className="inbox">
          {rows.map((row) =>
            row.ok ? (
              <li key={row.key}>
                <Link href={`/review/${row.key}`} className="inbox-row">
                  <div>
                    <strong>{row.player}</strong>
                    <span className="meta">{row.title} · {row.windows} windows · {row.accepted} accepted{row.queued ? ` · ${row.queued} analysing` : ""}</span>
                    {row.accepted + row.pending > 0 && (
                      <DecisionBar compact counts={{ accepted: row.accepted, rejected: 0, held: 0, waiting: row.pending, decided: row.accepted, total: row.accepted + row.pending }} />
                    )}
                  </div>
                  <span className="num">{row.pending} pending</span>
                  <span className="btn">Open</span>
                </Link>
              </li>
            ) : (
              <li key={row.key} className="error">{row.key}: this code no longer opens the submission.</li>
            ),
          )}
        </ul>
      )}
      <form
        className="join"
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = parseReviewLink(link);
          if (!parsed) {
            setMessage("Paste the full review link, including ?code=.");
            return;
          }
          rememberCode(parsed.key, parsed.code);
          router.push(`/review/${parsed.key}`);
        }}
      >
        <label>
          Review link
          <span className="join-controls">
            <input type="text" value={link} onChange={(event) => setLink(event.target.value)} />
            <button type="submit">Open</button>
          </span>
        </label>
      </form>
      {message && <p className="error">{message}</p>}
      </div>
    </main>
  );
}
