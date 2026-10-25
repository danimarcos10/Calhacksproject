"use client";

import Image from "next/image";
import Link from "next/link";
import { ViewTransition, useEffect, useRef, useState } from "react";
import { OutcomeStrip } from "@/components/Charts";
import { outcomeSplit } from "@/lib/visual";
import { CREDITS, SAMPLE } from "./content";
import { Decide } from "./Decide";
import { FollowScene } from "./FollowScene";
import { CardPhone, LandingMark, LanesPhone, PhotoPhone, SampleLanes } from "./Phones";

const rise = (index: number) => ({ "--i": index }) as React.CSSProperties;

export function Landing() {
  const root = useRef<HTMLDivElement>(null);
  const [nod, setNod] = useState(0);
  const [choice, setChoice] = useState<"scout" | "review">("scout");
  useScrollMotion(root);

  return (
    <ViewTransition exit="page-out" default="none">
      <div className="landing" ref={root}>
        <header className="l-top">
          <Link href="/" className="l-brand">
            <LandingMark cue={nod} />
            SecondLook
          </Link>
          <Link href="/review" className="l-link">Review inbox</Link>
        </header>

        <section className="l-hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <h1 id="hero-title" className="h-rise" style={rise(0)}>A second look at every touch.</h1>
            <p className="lead h-rise" style={rise(1)}>
              Upload a match clip and click your player once. SecondLook follows him, marks every receive, pass, carry and loss, and a coach accepts or rejects each moment.
            </p>
            <p className="actions h-rise" style={rise(2)}>
              <Link href="/scout" className="l-button">Start scouting</Link>
              <Link href="/review" className="l-text">Open the review inbox <span aria-hidden="true">→</span></Link>
            </p>
          </div>
          <div className="hero-stage">
            <div className="hero-photo">
              <Image src="/landing/stadium.jpg" width={2560} height={1042} alt="A floodlit stadium seen from the stands during an evening match." priority sizes="60vw" data-speed="0.06" />
            </div>
            <div className="hero-phone left" data-speed="-0.05"><LanesPhone /></div>
            <div className="hero-phone right" data-speed="-0.03"><CardPhone /></div>
            <div className="hero-phone front" data-speed="-0.08"><PhotoPhone /></div>
          </div>
        </section>

        <FollowScene />

        <section className="l-decide" aria-labelledby="decide-title">
          <h2 id="decide-title" className="rise" style={rise(0)}>The coach decides.</h2>
          <Decide onAccept={() => setNod((count) => count + 1)} />
          <p className="decide-note rise" style={rise(4)}>
            Every moment waits for a coach. Accepted ones go into the summary; rejected ones leave the counts. Try the middle row.
          </p>
        </section>

        <section className="l-counts" aria-labelledby="counts-title">
          <div className="counts-copy">
            <h2 id="counts-title" className="rise" style={rise(0)}>Every count opens its moments.</h2>
            <p className="rise" style={rise(1)}>
              The counts, the lanes and the confidence score are built from the same moments, so a tick on the lanes plays the footage behind it.
            </p>
            <p className="note rise" style={rise(2)}>
              Shown here: the sample review in this build, one 30-second clip with 7 moments, 3 of them accepted.
            </p>
          </div>
          <div className="counts-panel rise" style={rise(2)} data-ui="">
            <p className="panel-title">
              <strong>{SAMPLE.player}</strong>
              <span>{SAMPLE.clip} · tracked 29.5 s of 30 s</span>
            </p>
            <OutcomeStrip split={outcomeSplit(SAMPLE.moments)} trackedMs={SAMPLE.trackedMs} footageMs={SAMPLE.durationMs} />
            <SampleLanes />
          </div>
        </section>

        <section className="l-close" aria-labelledby="close-title">
          <Image className="close-photo" src="/landing/pitch.jpg" width={2400} height={1600} alt="An empty pitch under floodlights and heavy cloud before a match." sizes="100vw" />
          <div className="close-copy">
            <h2 id="close-title" className="rise" style={rise(0)}>Take a second look.</h2>
            <p className="rise" style={rise(1)}>Start with one clip. The review link it makes is the one a coach opens.</p>
          </div>
          <div className="close-dialog rise" style={rise(2)} data-ui="" role="group" aria-labelledby="dialog-title">
            <p id="dialog-title" className="dialog-title">Open SecondLook</p>
            <div className="segmented" role="radiogroup" aria-label="What you want to do">
              <button type="button" role="radio" aria-checked={choice === "scout"} onClick={() => setChoice("scout")}>Scout a player</button>
              <button type="button" role="radio" aria-checked={choice === "review"} onClick={() => setChoice("review")}>Review as a coach</button>
            </div>
            <p className="dialog-text">
              {choice === "scout"
                ? "Upload a clip, name the player and click him once. Tracking starts on the server."
                : "Paste the review link you were sent. Its moments wait for your decision."}
            </p>
            <Link href={choice === "scout" ? "/scout" : "/review"} className="dialog-button">
              {choice === "scout" ? "Start scouting" : "Open the review inbox"}
            </Link>
          </div>
        </section>

        <footer className="l-foot">
          <p className="credits-intro">Photographs from Wikimedia Commons.</p>
          <ul className="credits" aria-label="Photo credits">
            {Object.values(CREDITS).map((credit) => (
              <li key={credit.page}>
                <span className="credit-use">{credit.use}</span>
                <span>
                  <a href={credit.page} title={credit.title}>Photo</a> by {credit.creator},{" "}
                  <a href={credit.licenceUrl}>{credit.licence}</a>. {credit.change}
                </span>
              </li>
            ))}
          </ul>
          <div className="foot-line">
            <span>Footage review for youth football</span>
            <span className="foot-links">
              <Link href="/scout">Scout</Link>
              <Link href="/review">Review inbox</Link>
              <Link href="/workbench">Workbench</Link>
            </span>
            <span>2026</span>
          </div>
        </footer>
      </div>
    </ViewTransition>
  );
}

function useScrollMotion(root: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const page = root.current;
    if (!page) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scenes = [...page.querySelectorAll<HTMLElement>(".scene")];
    if (still) {
      scenes.forEach((scene) => scene.classList.add("is-rest"));
      return;
    }
    page.setAttribute("data-live", "");
    scenes.forEach((scene) => scene.classList.add("is-live"));

    const watch = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("in");
          watch.unobserve(entry.target);
        }
      },
      { threshold: 0.15 },
    );
    page.querySelectorAll(".rise").forEach((element) => watch.observe(element));

    const moving = [...page.querySelectorAll<HTMLElement>("[data-speed]")];
    let frame = 0;
    const update = () => {
      frame = 0;
      const height = window.innerHeight;
      for (const element of moving) {
        const box = element.parentElement?.getBoundingClientRect();
        if (!box || box.bottom < -height || box.top > height * 2) continue;
        const offset = (box.top + box.height / 2 - height / 2) * Number(element.dataset.speed);
        element.style.transform = `translate3d(0, ${offset.toFixed(1)}px, 0)`;
      }
      for (const scene of scenes) {
        const box = scene.getBoundingClientRect();
        const progress = Math.min(1, Math.max(0, -box.top / Math.max(1, box.height - height)));
        scene.style.setProperty("--p", progress.toFixed(3));
        scene.dataset.step = String(progress < 0.3 ? 0 : progress < 0.62 ? 1 : 2);
      }
    };
    const request = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", request);
    return () => {
      watch.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", request);
      window.removeEventListener("resize", request);
      page.removeAttribute("data-live");
    };
  }, [root]);
}
