"use client";

import Link from "next/link";
import { useQuery } from "convex/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../../convex/_generated/api";
import { knownEntries, parseReviewLink, rememberCode } from "@/lib/reviewAccess";

export function ReviewInbox() {
  const router = useRouter();
  const [entries, setEntries] = useState<{ key: string; code: string }[] | null>(null);
  const [link, setLink] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => setEntries(knownEntries()), []);
  const rows = useQuery(api.review.inbox, entries && entries.length ? { entries } : "skip");

  return (
    <main className="app">
      <header>
        <h1>Review inbox</h1>
        <p>Player submissions this browser has a review link for. Open one to watch its moments and record decisions.</p>
        <p className="meta"><Link href="/">Single-clip workbench</Link></p>
      </header>
      <section className="panel upload">
        {entries && entries.length === 0 && <p className="meta">No submission yet. Paste a review link below.</p>}
        {rows === undefined && entries && entries.length > 0 && <p className="meta">Loading…</p>}
        <ul className="inbox">
          {rows?.map((row) =>
            row.ok ? (
              <li key={row.key}>
                <Link href={`/review/${row.key}`}>
                  <strong>{row.player}</strong> · {row.title}
                </Link>
                <span className="meta">
                  {" "}· {row.windows} windows · {row.accepted} accepted · {row.pending} pending{row.queued ? ` · ${row.queued} analysing` : ""}
                </span>
              </li>
            ) : (
              <li key={row.key} className="error">{row.key}: this code no longer opens the submission.</li>
            ),
          )}
        </ul>
        <form
          className="row"
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
            <input type="text" value={link} onChange={(event) => setLink(event.target.value)} size={60} />
          </label>
          <button type="submit">Open</button>
        </form>
        {message && <p className="error">{message}</p>}
      </section>
    </main>
  );
}
