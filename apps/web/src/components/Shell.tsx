"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, ViewTransition, type ReactNode } from "react";
import { LookMark, LookProvider } from "@/components/Look";

const SetScopeContext = createContext<(label: string) => void>(() => {});

export function useScreenScope(label: string) {
  const setScope = useContext(SetScopeContext);
  useEffect(() => {
    setScope(label);
    return () => setScope("No submission open");
  }, [label, setScope]);
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState("No submission open");

  useEffect(() => setOpen(false), [pathname]);

  return (
    <LookProvider>
    <SetScopeContext.Provider value={setScope}>
      <div className="shell">
        <header className="phonebar">
          <button
            type="button"
            className="menu-toggle"
            aria-expanded={open}
            aria-controls="nav"
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Close" : "Menu"}
          </button>
          <Link href="/" className="brand">
            <LookMark />
            <span>SecondLook</span>
          </Link>
        </header>
        <aside id="nav" className={open ? "sidebar open" : "sidebar"}>
          <Link href="/" className="brand">
            <LookMark />
            <span>SecondLook</span>
          </Link>
          <p className="scope">{scope}</p>
          <nav className="nav" aria-label="Screens">
            <NavLink href="/scout" current={pathname === "/scout"}>Scout</NavLink>
            <NavLink href="/review" current={pathname.startsWith("/review") || pathname.startsWith("/prepare")}>Review</NavLink>
          </nav>
          <div className="sidebar-bottom">
            <p className="group-label">Builder</p>
            <NavLink href="/workbench" current={pathname === "/workbench"}>Workbench</NavLink>
          </div>
        </aside>
        <div className="canvas">
          <ViewTransition key={pathname} enter="page-in" exit="page-out" default="none">
            <div className="page">{children}</div>
          </ViewTransition>
        </div>
      </div>
    </SetScopeContext.Provider>
    </LookProvider>
  );
}

function NavLink({ href, current, children }: { href: string; current: boolean; children: ReactNode }) {
  return (
    <Link href={href} className="nav-item" aria-current={current ? "page" : undefined}>
      {children}
    </Link>
  );
}
