"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

type CueKind = "blink" | "nod" | "meet";
type Cue = { kind: CueKind; key: number };

type LookActions = {
  start: () => void;
  stop: () => void;
  cueOnce: (kind: "nod" | "meet") => void;
};

type LookState = {
  working: number;
  cue: Cue | null;
};

const LookActionsContext = createContext<LookActions | null>(null);
const LookStateContext = createContext<LookState>({ working: 0, cue: null });

export function LookProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [working, setWorking] = useState(0);
  const [cue, setCue] = useState<Cue | null>(null);
  const seenPath = useRef<string | null>(null);
  const key = useRef(0);

  const fire = useCallback((kind: CueKind) => {
    key.current += 1;
    setCue({ kind, key: key.current });
  }, []);

  const start = useCallback(() => setWorking((count) => count + 1), []);
  const stop = useCallback(() => setWorking((count) => Math.max(0, count - 1)), []);
  const cueOnce = useCallback((kind: "nod" | "meet") => fire(kind), [fire]);

  useEffect(() => {
    if (seenPath.current === null) {
      seenPath.current = pathname;
      return;
    }
    if (seenPath.current !== pathname) {
      seenPath.current = pathname;
      fire("blink");
    }
  }, [pathname, fire]);

  const actions = useMemo(() => ({ start, stop, cueOnce }), [start, stop, cueOnce]);
  const state = useMemo(() => ({ working, cue }), [working, cue]);

  return (
    <LookActionsContext.Provider value={actions}>
      <LookStateContext.Provider value={state}>{children}</LookStateContext.Provider>
    </LookActionsContext.Provider>
  );
}

export function useWorking(active: boolean) {
  const actions = useContext(LookActionsContext);
  useEffect(() => {
    if (!actions || !active) return;
    actions.start();
    return () => actions.stop();
  }, [active, actions]);
}

function noopCue(_kind: "nod" | "meet") {}

export function useCue() {
  const actions = useContext(LookActionsContext);
  return actions?.cueOnce ?? noopCue;
}

export function useLookState() {
  return useContext(LookStateContext);
}

export function LookMark({ className = "mark" }: { className?: string }) {
  const { working, cue } = useLookState();
  const mood = working > 0 ? "scan" : cue?.kind ?? "rest";
  return (
    <svg className={className} data-mood={mood} viewBox="0 0 28 16" aria-hidden="true">
      <rect className="look-line" x="0" y="6" width="28" height="4" rx="1" fill="currentColor" />
      <g key={cue?.key ?? 0}>
        <rect className="look-a" x="8" y="2" width="2" height="12" fill="currentColor" />
        <rect className="look-b" x="17" y="2" width="2" height="12" fill="currentColor" />
      </g>
    </svg>
  );
}
