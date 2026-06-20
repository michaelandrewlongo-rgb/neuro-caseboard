import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"
import { cn } from "@/lib/utils"

/* Grounded-Anatomical primitives: dark glass surfaces, 1px subtle borders, rounded corners.
   Change these (or the tokens in index.css) and every surface updates. */

// ---- Card / panel ---------------------------------------------------------------------------
export function Card({
  className,
  hover,
  ...props
}: HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return (
    <div
      className={cn(
        "border border-border bg-card",
        hover && "transition-opacity duration-150 hover:opacity-90",
        className,
      )}
      {...props}
    />
  )
}

// ---- Button ---------------------------------------------------------------------------------
const BTN_BASE =
  "inline-flex select-none items-center justify-center gap-2 border border-border font-bold uppercase tracking-wide transition-opacity duration-100 hover:opacity-80 active:opacity-70 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-muted-foreground disabled:opacity-50"
const BTN_VARIANTS = {
  primary: "bg-primary text-primary-foreground",
  outline: "bg-card text-foreground hover:bg-secondary",
  ghost: "border-transparent shadow-none text-foreground hover:bg-muted hover:translate-x-0 hover:translate-y-0",
} as const
const BTN_SIZES = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-5 py-2.5 text-sm",
} as const

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BTN_VARIANTS
  size?: keyof typeof BTN_SIZES
}) {
  return (
    <button className={cn(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)} {...props} />
  )
}

// ---- Badge / status chip --------------------------------------------------------------------
// Bright DTI fills (green/amber/red) carry near-black text per the two-token contrast model;
// the neutral tone is a dark panel with light text.
const BADGE_TONES = {
  success: "bg-success text-[#0a0a0a]",
  amber: "bg-amber text-[#0a0a0a]",
  signal: "bg-signal text-[#0a0a0a]",
  accent: "bg-accent text-accent-foreground",
  neutral: "bg-card text-foreground",
} as const

export function Badge({
  tone = "neutral",
  dot,
  className,
  children,
}: {
  tone?: keyof typeof BADGE_TONES
  dot?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border-2 border-border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider",
        BADGE_TONES[tone],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 bg-current" />}
      {children}
    </span>
  )
}

// ---- Eyebrow (mono micro-label) -------------------------------------------------------------
export function Eyebrow({
  className,
  children,
  accent,
}: {
  className?: string
  children: ReactNode
  accent?: boolean
}) {
  return <p className={cn("eyebrow", accent && "!text-[#6b93ff]", className)}>{children}</p>
}

// ---- Stat (metric) --------------------------------------------------------------------------
const STAT_VALUE_TONES = {
  success: "text-[#34e07f]",   /* sage bright — on-dark */
  amber: "text-[#ffc94d]",     /* ochre on-dark */
  signal: "text-destructive",  /* brick/critical */
  accent: "text-accent",
  neutral: "text-foreground",
} as const

export function Stat({
  value,
  label,
  tone = "neutral",
}: {
  value: ReactNode
  label: string
  tone?: keyof typeof STAT_VALUE_TONES
}) {
  return (
    <div className="border border-border bg-card px-4 py-3">
      <div className={cn("tnum font-display text-2xl font-bold leading-none", STAT_VALUE_TONES[tone])}>
        {value}
      </div>
      <div className="mt-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
    </div>
  )
}
