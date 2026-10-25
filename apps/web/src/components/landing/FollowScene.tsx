import Image from "next/image";
import { FOLLOW } from "./content";
import { Marks } from "./Marks";

const BEATS = [
  "Every player on the pitch gets a ring.",
  "Click your player once. The mark stays on him.",
  "His last few tenths of a second trail behind him, and the touch becomes a moment.",
];

export function FollowScene() {
  return (
    <section className="scene follow" data-scene="follow" aria-labelledby="follow-title">
      <div className="scene-stage">
        <div className="follow-text">
          <h2 id="follow-title">Follow one player.</h2>
          <ul className="beats">
            {BEATS.map((beat, index) => (
              <li key={beat} className="beat" data-beat={index}>{beat}</li>
            ))}
          </ul>
        </div>
        <figure className="follow-figure">
          <div className="follow-zoom">
            <Image src={FOLLOW.src} width={2400} height={1600} alt={FOLLOW.alt} sizes="(max-width: 860px) 100vw, 60vw" />
            <Marks id="follow" width={1500} height={1000} shot={FOLLOW} chip={FOLLOW.label} drift={-1} />
          </div>
        </figure>
      </div>
    </section>
  );
}
