import type { Spot } from "./content";

type Shot = {
  player: Spot;
  head: { x: number; y: number };
  ball: { x: number; y: number; r: number };
  others: Spot[];
  chipAt?: { x: number; y: number };
};

export function Marks({ id, width, height, shot, chip, drift = -1, chipFloor = 12 }: { id: string; width: number; height: number; shot: Shot; chip: string; drift?: number; chipFloor?: number }) {
  const { player, head, ball, others } = shot;
  const ry = player.rx * 0.32;
  const beamTop = Math.max(head.y, 0);
  const chipSize = width > 1000 ? 25 : 26;
  const chipWidth = chip.length * chipSize * 0.56 + chipSize * 1.2;
  const chipX = shot.chipAt?.x ?? Math.min(Math.max(head.x - chipWidth / 2, 12), width - chipWidth - 12);
  const chipY = shot.chipAt?.y ?? beamTop - chipSize * 2.2;
  return (
    <svg className="marks" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <pattern id={`hatch-${id}`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="7" stroke="#ffffff" strokeWidth="2" />
        </pattern>
        <clipPath id={`clip-${id}`}>
          <ellipse cx={player.x} cy={player.y} rx={player.rx} ry={ry} />
        </clipPath>
      </defs>
      <g className="m-rings">
        {[player, ...others].map((other) => (
          <ellipse key={`${other.x}-${other.y}`} cx={other.x} cy={other.y} rx={other.rx} ry={other.rx * 0.3} fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="2" />
        ))}
      </g>
      <g className="m-shadow" style={{ "--dx": `${drift * player.rx * 0.95}px` } as React.CSSProperties}>
        <line x1={player.x + drift * player.rx * 3.6} y1={player.y} x2={player.x} y2={player.y} stroke="rgba(255,255,255,0.6)" strokeWidth="3" strokeLinecap="round" />
        {[1, 2, 3, 4].map((step) => (
          <ellipse
            key={step}
            className="ghost"
            style={{ "--k": step } as React.CSSProperties}
            cx={player.x}
            cy={player.y}
            rx={player.rx * 0.92}
            ry={ry * 0.92}
            fill="rgba(96, 150, 232, 0.72)"
            stroke="rgba(255, 255, 255, 0.8)"
            strokeWidth="2"
          />
        ))}
      </g>
      <g className="m-marker">
        <polygon
          points={`${head.x - player.rx * 0.18},${beamTop} ${head.x + player.rx * 0.18},${beamTop} ${player.x + player.rx},${player.y} ${player.x - player.rx},${player.y}`}
          fill="rgba(255,255,255,0.2)"
        />
        <rect x={player.x - player.rx} y={player.y - ry} width={player.rx * 2} height={ry * 2} fill={`url(#hatch-${id})`} clipPath={`url(#clip-${id})`} opacity="0.85" />
        <ellipse cx={player.x} cy={player.y} rx={player.rx} ry={ry} fill="none" stroke="#1d5fbf" strokeWidth="4" />
        <ellipse cx={player.x} cy={player.y} rx={player.rx + 5} ry={ry + 5} fill="none" stroke="#ffffff" strokeWidth="1.5" />
      </g>
      <g className="m-ball">
        <circle cx={ball.x} cy={ball.y} r={ball.r} fill="none" stroke="#ffffff" strokeWidth="2.5" />
        <circle cx={ball.x} cy={ball.y} r={ball.r + 8} fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5" />
      </g>
      {chipY >= chipFloor && (
        <g className="m-chip">
          <rect x={chipX} y={chipY} width={chipWidth} height={chipSize * 1.7} rx={chipSize * 0.85} fill="rgba(10,10,10,0.8)" />
          <text x={chipX + chipWidth / 2} y={chipY + chipSize * 1.17} textAnchor="middle" fill="#ffffff" fontSize={chipSize} fontWeight="500">
            {chip}
          </text>
        </g>
      )}
    </svg>
  );
}
