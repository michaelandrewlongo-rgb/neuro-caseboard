import { stepStates } from "@/lib/loaderSteps"

/** Persistent, monotonic loader checklist: every stage is shown at once with a
    STATIC label (never blank) — earlier stages ✓done, the current ● active (pulsing),
    later ○ pending. Markers are decorative (aria-hidden); the loaders keep their own
    sr-only summary. Mono/compact to match the loaders' aesthetic. */
export default function StepChecklist({
  steps,
  current,
}: {
  steps: string[]
  current: number
}) {
  const states = stepStates(steps.length, current)

  return (
    <ul className="flex flex-col gap-2" aria-hidden>
      {steps.map((label, i) => {
        const state = states[i]
        return (
          <li key={i} className="flex items-center gap-3 font-mono text-sm">
            {state === "done" && (
              <span className="inline-block w-2 shrink-0 text-center text-muted-foreground">
                ✓
              </span>
            )}
            {state === "active" && (
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{
                  background: "#6b93ff",
                  boxShadow: "0 0 8px rgba(107,147,255,.7)",
                  animation: "pulse 2.4s ease-in-out infinite",
                }}
              />
            )}
            {state === "pending" && (
              <span className="inline-block w-2 shrink-0 text-center text-muted-foreground">
                ○
              </span>
            )}
            <span
              className={
                state === "active"
                  ? "text-foreground"
                  : state === "done"
                    ? "text-muted-foreground/80"
                    : "text-muted-foreground"
              }
            >
              {label}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
