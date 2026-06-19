import { Card } from "@/components/ui"

export default function RememberedPanel({ remembered }: { remembered: number }) {
  return (
    <Card className="bg-secondary p-4 text-sm">
      <p className="font-bold text-foreground">
        Board updated — {remembered} operative preference{remembered === 1 ? "" : "s"} now active in memory.
      </p>
      <p className="mt-1 text-muted-foreground">
        Your marks were applied and saved. These preferences carry to future boards of the same
        subspecialty. Decision-support only — verify against primary sources.
      </p>
    </Card>
  )
}
