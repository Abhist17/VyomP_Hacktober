import type { CSSProperties } from "react";

// A struck gold coin drawn in SVG and stacked in CSS 3D: two engraved faces and a milled
// edge built from thin discs. Its turn, tilt and position come from CSS variables set by
// the parent, so scroll can drive it without re-rendering React.
const EDGE_LAYERS = 14;

function Engraving({ id, side }: { id: string; side: "front" | "back" }) {
  const ring =
    side === "front"
      ? "VIVEKA · EVERY ENTRY IN ITS RIGHT PLACE · "
      : "27 VOUCHER TYPES · ONE CLEAR DECISION · ";
  return (
    <svg viewBox="0 0 200 200" aria-hidden="true">
      <defs>
        <path id={`${id}-ring`} d="M100,100 m-72,0 a72,72 0 1,1 144,0 a72,72 0 1,1 -144,0" />
        <radialGradient id={`${id}-dish`} cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#fff3c4" stopOpacity="0.55" />
          <stop offset="55%" stopColor="#d9a237" stopOpacity="0" />
          <stop offset="100%" stopColor="#6e480c" stopOpacity="0.35" />
        </radialGradient>
      </defs>
      {/* Milled rim and raised inner ring */}
      <circle
        cx="100"
        cy="100"
        r="95"
        fill="none"
        stroke="#7a5310"
        strokeWidth="3"
        strokeDasharray="1.2 2.2"
        opacity="0.7"
      />
      <circle
        cx="100"
        cy="100"
        r="88"
        fill="none"
        stroke="#fff0b8"
        strokeWidth="0.8"
        opacity="0.6"
      />
      <circle
        cx="100"
        cy="100"
        r="86.5"
        fill="none"
        stroke="#7a5310"
        strokeWidth="1.2"
        opacity="0.55"
      />
      <circle cx="100" cy="100" r="60" fill={`url(#${id}-dish)`} />
      <circle cx="100" cy="100" r="60" fill="none" stroke="#7a5310" strokeWidth="1" opacity="0.6" />
      <circle
        cx="100"
        cy="100"
        r="61"
        fill="none"
        stroke="#fff0b8"
        strokeWidth="0.6"
        opacity="0.5"
      />
      {/* Ring legend, struck twice for a light edge and a shadowed cut */}
      <text
        fontSize="9.6"
        letterSpacing="2.1"
        fontFamily="Georgia, serif"
        fill="#fff4c9"
        opacity="0.55"
        transform="translate(0.5 0.6)"
      >
        <textPath href={`#${id}-ring`}>{ring + ring}</textPath>
      </text>
      <text
        fontSize="9.6"
        letterSpacing="2.1"
        fontFamily="Georgia, serif"
        fill="#6e4a0c"
        opacity="0.8"
      >
        <textPath href={`#${id}-ring`}>{ring + ring}</textPath>
      </text>
      {side === "front" ? (
        <g fontFamily="Georgia, 'Noto Serif Devanagari', serif" textAnchor="middle">
          <text x="100.6" y="113.6" fontSize="40" fill="#fff4c9" opacity="0.55">
            विवेक
          </text>
          <text x="100" y="113" fontSize="40" fill="#6e4a0c" opacity="0.85">
            विवेक
          </text>
          <text x="100" y="136" fontSize="7" letterSpacing="3" fill="#6e4a0c" opacity="0.75">
            DISCERNMENT
          </text>
        </g>
      ) : (
        <g transform="translate(100 100)" opacity="0.8">
          {Array.from({ length: 12 }, (_, i) => (
            <ellipse
              key={i}
              rx="7"
              ry="25"
              cy="-25"
              fill="none"
              stroke="#6e4a0c"
              strokeWidth="1.1"
              transform={`rotate(${i * 30})`}
            />
          ))}
          <circle r="11" fill="#e4b04a" stroke="#6e4a0c" strokeWidth="1.2" />
          <text
            y="4.5"
            fontSize="12"
            textAnchor="middle"
            fontFamily="Georgia, serif"
            fill="#6e4a0c"
          >
            V+
          </text>
        </g>
      )}
    </svg>
  );
}

export function Coin({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return (
    <div className={`coin-scene ${className}`} style={style} aria-hidden="true">
      <div className="coin-glow" />
      <div className="coin">
        {Array.from({ length: EDGE_LAYERS }, (_, i) => (
          <span
            key={i}
            className="coin-edge"
            style={{ "--z": `${(i / (EDGE_LAYERS - 1) - 0.5) * 2}` } as CSSProperties}
          />
        ))}
        <div className="coin-face coin-front">
          <Engraving id="coin-front" side="front" />
          <span className="coin-sheen" />
        </div>
        <div className="coin-face coin-back">
          <Engraving id="coin-back" side="back" />
          <span className="coin-sheen" />
        </div>
      </div>
      <div className="coin-shadow" />
    </div>
  );
}
