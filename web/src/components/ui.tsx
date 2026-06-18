import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"
import { cn } from "@/lib/utils"

/* Neo-brutalist primitives: white surfaces, 2px black borders, hard offset shadows, square
   corners. Change these (or the tokens in index.css) and every surface updates. */

// ---- Card / panel ---------------------------------------------------------------------------
export function Card({
  className,
  hover,
  glow,
  ...props
}: HTMLAttributes<HTMLDivElement> & { hover?: boolean; glow?: boolean }) {
  return (
    <div
      className={cn(
        "border-2 border-border bg-card shadow-card",
        hover &&
          "transition-transform duration-100 hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-raised",
        glow && "shadow-raised",
        className,
      )}
      {...props}
    />
  )
}

// ---- Button ---------------------------------------------------------------------------------
const BTN_BASE =
  "inline-flex select-none items-center justify-center gap-2 border-2 border-border font-bold uppercase tracking-wide shadow-[var(--shadow-brutal-sm)] transition-all duration-100 hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-none active:translate-x-[3px] active:translate-y-[3px] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-[var(--shadow-brutal-sm)]"
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
const BADGE_TONES = {
  success: "bg-[var(--color-success)] text-white",
  amber: "bg-[var(--color-amber)] text-white",
  signal: "bg-primary text-primary-foreground",
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
  return <p className={cn("eyebrow", accent && "!text-primary", className)}>{children}</p>
}

// ---- Stat (metric) --------------------------------------------------------------------------
const STAT_VALUE_TONES = {
  success: "text-[var(--color-success)]",
  amber: "text-[var(--color-amber)]",
  signal: "text-primary",
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
    <div className="border-2 border-border bg-card px-4 py-3 shadow-[var(--shadow-brutal-sm)]">
      <div className={cn("tnum font-display text-2xl font-bold leading-none", STAT_VALUE_TONES[tone])}>
        {value}
      </div>
      <div className="mt-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
    </div>
  )
}
