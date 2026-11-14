import { CircleCheck, CircleHelp, Siren } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { VerdictKind } from "@/lib/types"

export const VERDICT = {
  ok: { label: "OK", icon: CircleCheck, text: "text-ok", bg: "bg-ok/15", border: "border-ok/40" },
  escalate: { label: "Escalate", icon: Siren, text: "text-escalate", bg: "bg-escalate/15", border: "border-escalate/40" },
  unknown: { label: "Unknown (no data)", icon: CircleHelp, text: "text-unknown", bg: "bg-unknown/15", border: "border-unknown/40" },
} satisfies Record<VerdictKind, unknown>

export function VerdictBadge({ verdict, className }: { verdict: VerdictKind; className?: string }) {
  const v = VERDICT[verdict]
  return (
    <Badge variant="outline" className={cn(v.text, v.border, v.bg, className)}>
      <v.icon />
      {v.label}
    </Badge>
  )
}

export function SeverityBadge({ severity }: { severity: string }) {
  if (!severity || severity === "none") return <Badge variant="secondary">No severity</Badge>
  const tone = severity === "sev1" ? "destructive" : "outline"
  return <Badge variant={tone}>{severity.toUpperCase()}</Badge>
}

export function Check({ ok, label }: { ok: boolean | null | undefined; label?: string }) {
  if (ok == null) return <span className="text-muted-foreground">n/a</span>
  return ok ? (
    <span className="inline-flex items-center gap-1 text-ok">
      <CircleCheck className="size-4" /> {label ?? "Correct"}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-escalate">
      <Siren className="size-4" /> {label ?? "Wrong"}
    </span>
  )
}
