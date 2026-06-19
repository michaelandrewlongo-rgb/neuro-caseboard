import { Card } from "@/components/ui"

export default function RememberedPanel({ remembered }: { remembered: number }) {
  return (
    <Card className="bg-secondary p-4 text-sm">
      <p className="font-bold text-foreground">
        Remembered {remembered} operative preference{remembered === 1 ? "" : "s"}.
      </p>
      <p className="mt-1 text-muted-foreground">
        The board below was regenerated with your marks applied. These preferences now carry to future
        boards of the same subspecialty. Decision-support only — verify against primary sources.
      </p>
    </Card>
  )
}
