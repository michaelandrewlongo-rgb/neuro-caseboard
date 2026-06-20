import { useEffect, useRef } from "react"
import type { CSSProperties } from "react"

/**
 * BrainTractography — whole-brain DTI tractography hero mark.
 *
 * Ported near-verbatim from the design reference
 * `docs/design/neuro-pages-latest/Neuro Landing.dc.html` (the `DCLogic`
 * canvas class). A deterministic LCG (seed 99173) builds a static fiber
 * field once into an offscreen buffer; travelling "action-potential" pulses
 * are composited over it each frame with the `lighter` blend mode.
 *
 * Faithfulness notes:
 *  - Every numeric constant (fiber counts, bezier control points, the six
 *    canonical DTI colours, pulse velocities) is preserved so the rendered
 *    field is identical to the prototype.
 *  - `componentDidMount`/`componentWillUnmount` → `useEffect` + cleanup.
 *  - `prefers-reduced-motion: reduce` → draw the static field once, skip the
 *    rAF pulse loop entirely (canvas animation isn't reachable by the global
 *    CSS reduced-motion guard in index.css, so we honour it here in JS).
 *  - The browser already pauses rAF in hidden tabs, so the app's
 *    `data-doc-hidden` pause (CSS-only) needs no canvas-specific handling.
 *
 * The engine draws into a fixed 480×480 design space and scales to the
 * canvas's CSS box, so the container controls the on-screen size.
 */

type Pt = { x: number; y: number }

interface Fiber {
  pts: Pt[]
  glowA: number
  coreA: number
  width: number
  flow: boolean
  high: boolean
  pulseHue: number
}

interface Pulse {
  f: Fiber
  n: number
  dir: number
  v: number
  len: number
  hue: number
  bright: number
  p: number
}

// The six canonical DTI directional colours [h, s, l] — orientation buckets:
// red = L–R (commissural), yellow/magenta = gentle oblique, green/cyan = steep
// oblique (association), blue = S–I (corticospinal).
const DTI6: ReadonlyArray<readonly [number, number, number]> = [
  [0, 100, 67], // RED     — horizontal: L–R commissural / crossing the midline
  [43, 100, 64], // YELLOW  — gentle oblique: the transitional orientation
  [146, 72, 52], // GREEN   — steep oblique: association fibres linking regions
  [222, 100, 71], // BLUE    — vertical: S–I corticospinal tract / the spine
  [183, 79, 55], // CYAN    — steep oblique: literature-axis blend
  [314, 100, 71], // MAGENTA — gentle oblique: deck-axis blend
]

class TractographyEngine {
  private seed = 99173
  private readonly canvas: HTMLCanvasElement
  private readonly animate: boolean

  private base: HTMLCanvasElement | null = null
  private fibers: Fiber[] | null = null
  private flow: Fiber[] = []
  private high: Fiber[] = []
  private pulses: Pulse[] | null = null

  private dpr = 1
  private cssW = 0
  private cssH = 0
  private raf = 0
  private last = 0
  private dead = false

  private readonly onResize = () => this.setup()

  constructor(canvas: HTMLCanvasElement, animate: boolean) {
    this.canvas = canvas
    this.animate = animate
  }

  // deterministic LCG → reproducible field
  private r(): number {
    this.seed = (this.seed * 1664525 + 1013904223) >>> 0
    return this.seed / 4294967296
  }

  // sample a cubic bezier into a wiggly polyline (organic fibre)
  private fiber(
    p0: number[],
    p1: number[],
    p2: number[],
    p3: number[],
    n: number,
    wig: number,
  ): Pt[] {
    const pts: Pt[] = []
    const ph1 = this.r() * 6.283
    const ph2 = this.r() * 6.283
    const amp = wig * (0.5 + this.r() * 0.9)
    for (let i = 0; i <= n; i++) {
      const t = i / n
      const u = 1 - t
      const x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
      const y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
      const dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
      const dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
      const len = Math.hypot(dx, dy) || 1
      const nx = -dy / len
      const ny = dx / len
      const env = Math.sin(Math.PI * t)
      const w =
        (Math.sin(t * 3.5 + ph1) + 0.45 * Math.sin(t * 8.8 + ph2) + 0.22 * Math.sin(t * 14.2 + ph1 * 1.6)) *
        amp *
        env
      pts.push({ x: x + nx * w, y: y + ny * w })
    }
    return pts
  }

  private build(): Fiber[] {
    const F: Fiber[] = []
    const cx = 240
    const R = () => this.r()
    const push = (pts: Pt[], opts?: Partial<Fiber>) => {
      F.push(
        Object.assign(
          { pts, glowA: 0.018, coreA: 0.5, width: 0.5, flow: false, high: false, pulseHue: 222 },
          opts || {},
        ) as Fiber,
      )
    }
    // colour comes from each segment's direction in stroke() (DTI)
    const ECX = cx
    const ECY = 216
    const WX = 170
    const HY = 148 // cerebral boundary

    const NECK = 350 // where the brain funnels into the cord
    // lateral ventricles — CSF voids flanking the midline; fibres route around them (none cross)
    const VENT = [
      [cx - 30, 196],
      [cx + 30, 196],
    ]
    const inVent = (x: number, y: number) => {
      for (const v of VENT) {
        const a = (x - v[0]) / 18
        const b = (y - v[1]) / 44
        if (a * a + b * b < 1) return true
      }
      return false
    }
    const clear = (pts: Pt[]) => {
      for (let k = 1; k < pts.length - 1; k++) {
        if (inVent(pts[k].x, pts[k].y)) return false
      }
      return true
    }

    // ── corticospinal / corona radiata — CONTINUOUS fibres: spinal cord → narrow brainstem neck → fan to cortex ──
    for (let i = 0; i < 580; i++) {
      const th = -0.34 + R() * (Math.PI + 0.68) // cortical target, lower-lateral → crown → lower-lateral
      const rr = 0.5 + R() * 0.46
      const bx = ECX + WX * Math.cos(th) * rr // cortex endpoint
      const by = ECY - HY * Math.sin(th) * rr
      const sx = cx + (R() - 0.5) * 12 // cord origin (narrow, near midline)
      const sy = 444 + R() * 30
      const neckX = cx + (R() - 0.5) * 14
      const Tn = Math.hypot(WX * Math.sin(th), HY * Math.cos(th)) || 1
      const tx = (-WX * Math.sin(th)) / Tn
      const ty = (HY * Math.cos(th)) / Tn // cortical-surface tangent
      const hook = (R() < 0.5 ? 1 : -1) * (10 + R() * 22) * rr
      const c1 = [neckX, NECK + R() * 14] // pinch through the brainstem (keeps the cord narrow)
      const c2 = [bx + tx * hook, by + ty * hook] // hook along the cortical surface
      const pts = this.fiber([sx, sy], c1, c2, [bx, by], 36, 2 + R() * 2.2)
      if (!clear(pts)) continue // route around the lateral ventricles
      push(pts, {
        coreA: 0.2 + R() * 0.24,
        width: 0.32 + R() * 0.4,
        flow: R() < 0.16,
        high: R() < 0.4,
        pulseHue: 222,
      })
    }

    // ── spinal cord density — short fibres filling the cord below the neck ──
    for (let i = 0; i < 90; i++) {
      const oy = NECK - 6 + R() * 30
      const x0 = cx + (R() - 0.5) * 15
      const len = 96 + R() * 44
      const sway = (R() - 0.5) * 13
      const xMid = cx + sway * 0.5
      const xEnd = cx + (R() - 0.5) * 8
      push(
        this.fiber(
          [x0, oy],
          [xMid, oy + len * 0.34],
          [xEnd - sway * 0.4, oy + len * 0.7],
          [xEnd, oy + len],
          24,
          1.4 + R() * 2,
        ),
        { coreA: 0.34 + R() * 0.22, width: 0.44 + R() * 0.4, flow: R() < 0.55, high: R() < 0.5, pulseHue: 222 },
      )
    }

    // ── callosal radiations — fibres rise from the midline body and fan UP to the cortex ──
    for (let i = 0; i < 150; i++) {
      const side = R() < 0.5 ? -1 : 1
      const ox = cx + side * (4 + R() * 16) // origin just off the midline, above the ventricles
      const oy = 150 + R() * 18
      const th = 0.5 + R() * 0.9 // aim up-and-out to the cortex
      const rr = 0.7 + R() * 0.3
      const bx = ECX + side * WX * Math.cos(th) * rr
      const by = ECY - HY * Math.sin(th) * rr
      const pts = this.fiber(
        [ox, oy],
        [ox + side * 10, oy - 20 - R() * 20],
        [bx - side * 24, (oy + by) / 2],
        [bx, by],
        20,
        1.5 + R() * 2,
      )
      if (!clear(pts)) continue
      push(pts, { coreA: 0.26 + R() * 0.28, width: 0.36 + R() * 0.36, flow: R() < 0.16, pulseHue: 0 })
    }

    // ── longitudinal association — tall vertical green sweeps along each hemisphere ──
    for (let i = 0; i < 210; i++) {
      const side = R() < 0.5 ? -1 : 1
      const xb = cx + side * (66 + R() * 74)
      const topY = 116 + R() * 56
      const botY = 276 + R() * 72
      const bowx = (R() - 0.5) * 44
      const pts = this.fiber(
        [xb + (R() - 0.5) * 16, topY],
        [xb + bowx, topY + (botY - topY) * 0.33],
        [xb - bowx, topY + (botY - topY) * 0.66],
        [xb + (R() - 0.5) * 16, botY],
        22,
        2 + R() * 2.4,
      )
      if (!clear(pts)) continue
      push(pts, { coreA: 0.22 + R() * 0.26, width: 0.34 + R() * 0.36, flow: R() < 0.12, pulseHue: 146 })
    }

    // ── cortical mantle — short fibres hugging the boundary, tracing the rounded cerebral outline ──
    for (let i = 0; i < 320; i++) {
      const th0 = -0.3 + R() * (Math.PI + 0.6)
      const dir = R() < 0.5 ? 1 : -1
      const arc = 0.12 + R() * 0.18
      const th1 = th0 + dir * arc
      const rA = 0.9 + R() * 0.12
      const p0 = [ECX + WX * Math.cos(th0) * rA, ECY - HY * Math.sin(th0) * rA]
      const p3 = [ECX + WX * Math.cos(th1) * rA, ECY - HY * Math.sin(th1) * rA]
      const thm = (th0 + th1) / 2
      const rM = rA * (0.95 + R() * 0.09)
      const pm = [ECX + WX * Math.cos(thm) * rM, ECY - HY * Math.sin(thm) * rM]
      push(this.fiber(p0, pm, pm, p3, 12, 1 + R() * 1.4), {
        coreA: 0.2 + R() * 0.22,
        width: 0.3 + R() * 0.3,
        flow: R() < 0.1,
        pulseHue: 183,
      })
    }

    return F
  }

  private stroke(ctx: CanvasRenderingContext2D, f: Fiber, glow: boolean) {
    const pts = f.pts
    const n = pts.length
    for (let i = 0; i < n - 1; i++) {
      const t = i / (n - 1)
      const fade = Math.sin(Math.PI * Math.min(Math.max(t, 0.001), 0.999))
      // DTI directional colour from the local tangent
      const i0 = Math.max(0, i - 1)
      const i1 = Math.min(n - 1, i + 2)
      const sdx = pts[i1].x - pts[i0].x
      const sdy = pts[i1].y - pts[i0].y
      // fold orientation to [0,180), quantise to the six canonical DTI colours
      let ori = Math.atan2(sdy, sdx)
      if (ori < 0) ori += Math.PI
      const C = DTI6[Math.round(ori / 0.5235987755982988) % 6] // 30° buckets
      const a = (glow ? f.glowA : f.coreA) * (0.3 + 0.7 * fade)
      ctx.strokeStyle = `hsla(${C[0]},${C[1]}%,${(glow ? C[2] - 14 : C[2]).toFixed(0)}%,${a.toFixed(3)})`
      ctx.lineWidth = glow ? f.width * 2.0 : f.width
      ctx.beginPath()
      ctx.moveTo(pts[i].x, pts[i].y)
      ctx.lineTo(pts[i + 1].x, pts[i + 1].y)
      ctx.stroke()
    }
  }

  // build the static tract bundle once into an offscreen buffer; size the live canvas
  private setup(): boolean {
    const cv = this.canvas
    const cssW = cv.clientWidth
    const cssH = cv.clientHeight
    if (!cssW || !cssH) return false
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    cv.width = Math.round(cssW * dpr)
    cv.height = Math.round(cssH * dpr)
    this.dpr = dpr
    this.cssW = cssW
    this.cssH = cssH
    const fibers = this.fibers || (this.fibers = this.build())
    this.flow = fibers.filter((f) => f.flow)
    this.high = this.flow.filter((f) => f.high)
    const base = this.base || (this.base = document.createElement("canvas"))
    base.width = cv.width
    base.height = cv.height
    const bx = base.getContext("2d")
    if (!bx) return false
    bx.setTransform(dpr, 0, 0, dpr, 0, 0)
    bx.clearRect(0, 0, cssW, cssH)
    bx.scale(cssW / 480, cssH / 480)
    bx.lineCap = "round"
    bx.lineJoin = "round"
    bx.globalCompositeOperation = "lighter"
    for (const f of fibers) this.stroke(bx, f, true) // density glow
    for (const f of fibers) this.stroke(bx, f, false) // crisp cores
    bx.globalCompositeOperation = "source-over"
    if (!this.pulses) {
      this.pulses = []
      for (let i = 0; i < 54; i++) {
        const p = {} as Pulse
        this.resetPulse(p, true)
        this.pulses.push(p)
      }
    }
    return true
  }

  // a travelling action-potential along one fibre
  private resetPulse(ps: Pulse, init: boolean) {
    const pool = this.high.length && this.r() < 0.6 ? this.high : this.flow
    const f = pool[(this.r() * pool.length) | 0] || this.flow[0]
    ps.f = f
    ps.n = f.pts.length
    ps.dir = f.high && this.r() < 0.45 ? -1 : 1 // highways fire both ways: brain↔spine
    ps.v = 0.0028 + this.r() * 0.006 // points per ms (gentle drift)
    ps.len = 9 + ((this.r() * 9) | 0)
    ps.hue = f.pulseHue != null ? f.pulseHue : DTI6[3][0]
    ps.bright = 0.5 + this.r() * 0.4
    ps.p = ps.dir > 0 ? -ps.len * this.r() : ps.n - 1 + ps.len * this.r()
    if (init) ps.p = this.r() * (ps.n - 1)
  }

  private drawPulses(ctx: CanvasRenderingContext2D) {
    if (!this.pulses) return
    for (const ps of this.pulses) {
      const pts = ps.f.pts
      const n = ps.n
      for (let k = 0; k < ps.len; k++) {
        const idx = ps.p - ps.dir * k
        if (idx < 0 || idx > n - 1) continue
        const i0 = Math.floor(idx)
        const fr = idx - i0
        const a0 = pts[i0]
        const a1 = pts[Math.min(i0 + 1, n - 1)]
        const x = a0.x + (a1.x - a0.x) * fr
        const y = a0.y + (a1.y - a0.y) * fr
        const tt = k / ps.len
        const al = (1 - tt) * (1 - tt) * ps.bright
        if (k === 0) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, 5.5)
          g.addColorStop(0, `hsla(${ps.hue},100%,93%,${ps.bright.toFixed(3)})`)
          g.addColorStop(0.4, `hsla(${ps.hue},100%,72%,${(ps.bright * 0.5).toFixed(3)})`)
          g.addColorStop(1, `hsla(${ps.hue},100%,60%,0)`)
          ctx.fillStyle = g
          ctx.beginPath()
          ctx.arc(x, y, 5.5, 0, 6.283)
          ctx.fill()
        }
        ctx.fillStyle = `hsla(${ps.hue},96%,${(86 - tt * 32).toFixed(0)}%,${al.toFixed(3)})`
        ctx.beginPath()
        ctx.arc(x, y, k === 0 ? 1.7 : 1.25, 0, 6.283)
        ctx.fill()
      }
    }
  }

  // composite the static base into the live canvas (shared by the static and animated paths)
  private paintBase(ctx: CanvasRenderingContext2D) {
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    if (this.base) ctx.drawImage(this.base, 0, 0)
  }

  private tick = (ts: number) => {
    if (this.dead) return
    let dt = ts - (this.last || ts)
    this.last = ts
    if (dt > 60) dt = 60
    if (this.pulses) {
      for (const ps of this.pulses) {
        ps.p += ps.v * ps.dir * dt
        if (ps.p < -ps.len || ps.p > ps.n - 1 + ps.len) this.resetPulse(ps, false)
      }
    }
    const ctx = this.canvas.getContext("2d")
    if (!ctx) {
      this.raf = requestAnimationFrame(this.tick)
      return
    }
    this.paintBase(ctx)
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    ctx.scale(this.cssW / 480, this.cssH / 480)
    ctx.globalCompositeOperation = "lighter"
    this.drawPulses(ctx)
    ctx.globalCompositeOperation = "source-over"
    this.raf = requestAnimationFrame(this.tick)
  }

  start() {
    if (this.setup()) {
      cancelAnimationFrame(this.raf)
      if (this.animate) {
        this.last = 0
        this.raf = requestAnimationFrame(this.tick)
      } else {
        // reduced motion: paint the static field once, no pulse loop
        const ctx = this.canvas.getContext("2d")
        if (ctx) this.paintBase(ctx)
      }
    } else {
      this.raf = requestAnimationFrame(() => this.start())
    }
    window.addEventListener("resize", this.onResize)
  }

  stop() {
    this.dead = true
    cancelAnimationFrame(this.raf)
    window.removeEventListener("resize", this.onResize)
  }
}

interface BrainTractographyProps {
  className?: string
  style?: CSSProperties
}

export default function BrainTractography({ className, style }: BrainTractographyProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const engine = new TractographyEngine(canvas, !reduce)
    engine.start()
    return () => engine.stop()
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: "100%", height: "100%", display: "block", ...style }}
      aria-hidden="true"
    />
  )
}
