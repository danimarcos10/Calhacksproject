"use client";

import { useState } from "react";

type State = "suggestion" | "accepted" | "rejected";

function Row({ state, live, onDecide }: { state: State; live?: boolean; onDecide?: (next: State) => void }) {
  const label = state === "accepted" ? "Accepted" : state === "rejected" ? "Rejected" : "AI suggestion";
  return (
    <div className={`decide-row ${state}${live ? " live" : ""}`} data-ui="">
      <span className={`key ${state === "suggestion" ? "outline" : state === "accepted" ? "accepted" : "rejected"}`} aria-hidden="true" />
      <span className="decide-main">
        <span className="decide-line">
          <strong>Clip 1</strong> <strong>Loss</strong> <span className="num">0:18.800</span> Loses the ball to an opponent
        </span>
        <span className="decide-meta">lost · {label}</span>
      </span>
      {live && state === "suggestion" && (
        <span className="decide-actions">
          <button type="button" onClick={() => onDecide?.("accepted")}>Accept</button>
          <button type="button" onClick={() => onDecide?.("rejected")}>Reject</button>
        </span>
      )}
      {live && state !== "suggestion" && (
        <span className="decide-actions">
          <button type="button" onClick={() => onDecide?.("suggestion")}>Undo</button>
        </span>
      )}
      {!live && <span className={`decide-pill ${state}`}>{label}</span>}
    </div>
  );
}

export function Decide({ onAccept }: { onAccept: () => void }) {
  const [state, setState] = useState<State>("suggestion");
  return (
    <div className="decide">
      <div className="decide-step rise" style={{ "--i": 1 } as React.CSSProperties}>
        <p className="decide-word">Arrives</p>
        <Row state="suggestion" />
      </div>
      <div className="decide-step rise" style={{ "--i": 2 } as React.CSSProperties}>
        <p className="decide-word">Checked</p>
        <Row
          state={state}
          live
          onDecide={(next) => {
            setState(next);
            if (next === "accepted") onAccept();
          }}
        />
      </div>
      <div className="decide-step rise flip" style={{ "--i": 3 } as React.CSSProperties}>
        <p className="decide-word">Decided</p>
        <Row state="accepted" />
      </div>
    </div>
  );
}
