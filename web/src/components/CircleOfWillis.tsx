/**
 * CircleOfWillis — Hero anatomical SVG animation.
 *
 * Near-verbatim port of the Circle-of-Willis SVG from the design handoff
 * (`.project-loop/design_handoff/Neuro Landing.dc.html`).
 *
 * Keyframes live in `web/src/index.css`:
 *   nl-float   — outer wrapper bob (Task 1)
 *   nl-sweep   — telemetry scan beam (Task 1)
 *   nl-flow    — Willis-ring flow pulse (Task 1)
 *   nl-node    — anastomosis node halo pulse (Task 1)
 *   nl-flowb   — basilar-artery flow pulse (Task 8a)
 *
 * `prefers-reduced-motion` is honored globally by the
 * `animation-duration: 0.01ms !important` guard in index.css.
 *
 * Pass `className` / `style` to let Task 8b size this from outside.
 */
import type { CSSProperties } from "react"

interface CircleOfWillisProps {
  className?: string
  style?: CSSProperties
}

export default function CircleOfWillis({ className, style }: CircleOfWillisProps) {
  return (
    <div
      className={className}
      style={{
        position: "relative",
        width: "100%",
        maxWidth: 500,
        justifySelf: "center",
        aspectRatio: "400 / 470",
        ...style,
      }}
    >
      {/* radial glow backdrop behind the SVG */}
      <div
        style={{
          position: "absolute",
          inset: "8% 8% 20%",
          borderRadius: "50%",
          background:
            "radial-gradient(circle at 50% 42%, rgba(255,115,99,0.16), rgba(150,30,45,0.06) 55%, transparent 70%)",
          filter: "blur(10px)",
        }}
      />

      {/* floating SVG wrapper — nl-float bobs gently */}
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          animation: "nl-float 7s ease-in-out infinite",
        }}
      >
        <svg
          viewBox="0 0 400 470"
          width="100%"
          height="100%"
          style={{ overflow: "visible" }}
        >
          <defs>
            {/* vessel gradient: arterial crimson (bright) → crimson → deep crimson */}
            <linearGradient
              id="cowVessel"
              gradientUnits="userSpaceOnUse"
              x1="200"
              y1="24"
              x2="200"
              y2="440"
            >
              <stop offset="0%" stopColor="#ff7363" />
              <stop offset="42%" stopColor="#e23b3b" />
              <stop offset="100%" stopColor="#a01f2b" />
            </linearGradient>

            {/* anastomosis node: white-hot core fading to transparent crimson edge */}
            <radialGradient id="cowNode" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="35%" stopColor="#ffb3a8" />
              <stop offset="100%" stopColor="rgba(255,115,99,0)" />
            </radialGradient>

            {/* telemetry sweep-beam fill */}
            <radialGradient
              id="cowBeam"
              gradientUnits="userSpaceOnUse"
              cx="200"
              cy="208"
              r="180"
            >
              <stop offset="0%" stopColor="rgba(255,115,99,0.22)" />
              <stop offset="100%" stopColor="rgba(255,115,99,0)" />
            </radialGradient>

            {/* soft bloom filter for the glow vessel pass */}
            <filter id="cowGlow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation={4.5} />
            </filter>

            {/* vessel tree — defined once, drawn twice (bloom + crisp) */}
            <g
              id="cowV"
              fill="none"
              stroke="url(#cowVessel)"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* Circle of Willis ring: AComm → L ACA → L ICA → L PComm/PCA → basilar tip → R PCA → R ICA → R ACA */}
              <path
                d="M200,68 C176,92 158,132 148,172 C142,200 150,228 162,250 C176,258 188,262 200,262 C212,262 224,258 238,250 C250,228 258,200 252,172 C242,132 224,92 200,68 Z"
                strokeWidth="4.6"
              />
              {/* anterior cerebral A2 extensions above AComm */}
              <path d="M200,68 C196,52 193,44 191,33" strokeWidth="3" />
              <path d="M200,68 C204,52 207,44 209,33" strokeWidth="3" />
              {/* left MCA candelabra */}
              <path d="M148,172 C116,176 92,188 70,198" strokeWidth="4" />
              <path d="M70,198 C58,190 50,185 41,180" strokeWidth="2.4" />
              <path d="M70,198 C57,198 49,200 39,201" strokeWidth="2.4" />
              <path d="M70,198 C58,206 51,212 45,221" strokeWidth="2.4" />
              {/* right MCA candelabra */}
              <path d="M252,172 C284,176 308,188 330,198" strokeWidth="4" />
              <path d="M330,198 C342,190 350,185 359,180" strokeWidth="2.4" />
              <path d="M330,198 C343,198 351,200 361,201" strokeWidth="2.4" />
              <path d="M330,198 C342,206 349,212 355,221" strokeWidth="2.4" />
              {/* posterior cerebral P2 extensions */}
              <path d="M162,250 C140,258 121,263 103,266" strokeWidth="3.2" />
              <path d="M238,250 C260,258 279,263 297,266" strokeWidth="3.2" />
              {/* basilar artery */}
              <path d="M200,262 C198,290 202,318 200,346" strokeWidth="6" />
              {/* pontine / cerebellar twigs off basilar */}
              <path d="M198,300 C190,303 184,306 178,310" strokeWidth="1.8" />
              <path d="M202,300 C210,303 216,306 222,310" strokeWidth="1.8" />
              {/* vertebral arteries forming the basilar */}
              <path d="M200,346 C194,372 182,398 170,420" strokeWidth="5" />
              <path d="M200,346 C206,372 218,398 230,420" strokeWidth="5" />
            </g>
          </defs>

          {/* telemetry backdrop — dashed outer ring + inner ring + rotating scan beam */}
          <g opacity={0.6}>
            <circle
              cx="200"
              cy="206"
              r="186"
              fill="none"
              stroke="rgba(255,255,255,0.05)"
              strokeDasharray="2 9"
            />
            <circle
              cx="200"
              cy="206"
              r="150"
              fill="none"
              stroke="rgba(255,255,255,0.04)"
            />
            <g
              style={{
                transformOrigin: "200px 206px",
                animation: "nl-sweep 16s linear infinite",
              }}
            >
              <path
                d="M200,206 L150,40 A175,175 0 0 1 250,40 Z"
                fill="url(#cowBeam)"
              />
            </g>
          </g>

          {/* vessels: soft bloom pass, then crisp pass */}
          <use href="#cowV" filter="url(#cowGlow)" opacity={0.55} />
          <use href="#cowV" />

          {/* pulsatile flow tracing the Willis ring — two offset pulses */}
          <path
            d="M200,68 C176,92 158,132 148,172 C142,200 150,228 162,250 C176,258 188,262 200,262 C212,262 224,258 238,250 C250,228 258,200 252,172 C242,132 224,92 200,68 Z"
            pathLength={240}
            fill="none"
            stroke="#ffe6df"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeDasharray="4 236"
            style={{
              filter: "drop-shadow(0 0 4px #ff8a7a)",
              animation: "nl-flow 3.4s linear infinite",
            }}
          />
          <path
            d="M200,68 C176,92 158,132 148,172 C142,200 150,228 162,250 C176,258 188,262 200,262 C212,262 224,258 238,250 C250,228 258,200 252,172 C242,132 224,92 200,68 Z"
            pathLength={240}
            fill="none"
            stroke="#ffd9cf"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="3 237"
            style={{
              filter: "drop-shadow(0 0 4px #ff8a7a)",
              animation: "nl-flow 3.4s linear infinite",
              animationDelay: "-1.7s",
            }}
          />
          {/* pulsatile flow up the basilar artery */}
          <path
            d="M200,346 C202,318 198,290 200,262"
            pathLength={90}
            fill="none"
            stroke="#ffe6df"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeDasharray="5 85"
            style={{
              filter: "drop-shadow(0 0 4px #ff8a7a)",
              animation: "nl-flowb 2.2s linear infinite",
            }}
          />

          {/* anastomosis nodes — radial halo pulse + bright core dot */}
          <g>
            {/* pulsing halo circles */}
            <circle
              cx={200}
              cy={68}
              r={13}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 2.8s ease-in-out infinite",
              }}
            />
            <circle
              cx={148}
              cy={172}
              r={12}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 3.1s ease-in-out infinite",
                animationDelay: "-0.6s",
              }}
            />
            <circle
              cx={252}
              cy={172}
              r={12}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 3.1s ease-in-out infinite",
                animationDelay: "-1.4s",
              }}
            />
            <circle
              cx={162}
              cy={250}
              r={11}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 2.9s ease-in-out infinite",
                animationDelay: "-0.9s",
              }}
            />
            <circle
              cx={238}
              cy={250}
              r={11}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 2.9s ease-in-out infinite",
                animationDelay: "-2.0s",
              }}
            />
            <circle
              cx={200}
              cy={262}
              r={12}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 3.3s ease-in-out infinite",
                animationDelay: "-1.1s",
              }}
            />
            <circle
              cx={200}
              cy={346}
              r={10}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 3.0s ease-in-out infinite",
                animationDelay: "-0.3s",
              }}
            />
            <circle
              cx={70}
              cy={198}
              r={8}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 2.7s ease-in-out infinite",
                animationDelay: "-1.8s",
              }}
            />
            <circle
              cx={330}
              cy={198}
              r={8}
              fill="url(#cowNode)"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: "nl-node 2.7s ease-in-out infinite",
                animationDelay: "-0.5s",
              }}
            />

            {/* bright core dots at each anastomosis point */}
            <circle cx={200} cy={68} r={3.4} fill="#fff2ee" />
            <circle cx={148} cy={172} r={3} fill="#fff2ee" />
            <circle cx={252} cy={172} r={3} fill="#fff2ee" />
            <circle cx={162} cy={250} r={2.8} fill="#fff2ee" />
            <circle cx={238} cy={250} r={2.8} fill="#fff2ee" />
            <circle cx={200} cy={262} r={3} fill="#fff2ee" />
            <circle cx={200} cy={346} r={2.6} fill="#fff2ee" />
          </g>

          {/* anatomical micro-labels */}
          <g
            fill="#8a7d77"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="8.5"
            letterSpacing="0.04em"
          >
            <text x="200" y="22" textAnchor="middle">ACA</text>
            <text x="30" y="176" textAnchor="start">MCA</text>
            <text x="370" y="176" textAnchor="end">MCA</text>
            <text x="92" y="284" textAnchor="start">PCA</text>
            <text x="308" y="284" textAnchor="end">PCA</text>
            <text x="214" y="306" textAnchor="start">BA</text>
            <text x="150" y="438" textAnchor="middle">VA</text>
            <text x="250" y="438" textAnchor="middle">VA</text>
          </g>
        </svg>
      </div>

      {/* anatomical caption below the SVG */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: -2,
          transform: "translateX(-50%)",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10,
          letterSpacing: "0.22em",
          color: "#766a64",
          whiteSpace: "nowrap",
        }}
      >
        CIRCLE OF WILLIS · ARTERIAL ANASTOMOSIS
      </div>
    </div>
  )
}
