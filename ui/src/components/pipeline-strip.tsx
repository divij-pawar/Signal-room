import { ArrowRight, Bot, Database, Inbox, MessageSquare, Radar, Search } from "lucide-react"
import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

export type PipelineCounts = {
  hosts: string
  logs: number
  windows: number
  skipped: number
  escalations: number
  reports: number
  posts: number
}

type Node = { icon: LucideIcon; title: string; value: string; detail: string; active?: boolean }

/** Watchers → Telemetry → Guardian → Queue → RCA → Slack, with what passed through each stage. */
export function PipelineStrip({ counts, highlight }: { counts: PipelineCounts; highlight?: string }) {
  const nodes: Node[] = [
    { icon: Radar, title: "Watchers", value: counts.hosts, detail: "hosts reporting" },
    { icon: Database, title: "Telemetry", value: counts.logs.toLocaleString(), detail: "log records" },
    {
      icon: Search,
      title: "Guardian",
      value: String(counts.windows),
      detail: `windows · ${counts.skipped} without a model call`,
    },
    { icon: Inbox, title: "Queue", value: String(counts.escalations), detail: "escalations" },
    { icon: Bot, title: "RCA agent", value: String(counts.reports), detail: "root cause reports" },
    { icon: MessageSquare, title: "Slack", value: String(counts.posts), detail: "alerts (Sev 1–2)" },
  ]
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:flex xl:items-stretch">
      {nodes.map((n, i) => (
        <div key={n.title} className="flex min-w-0 flex-1 items-center gap-2">
          <div
            className={cn(
              "flex min-w-0 flex-1 items-center gap-3 rounded-lg border bg-card p-3",
              highlight === n.title && "border-rca ring-2 ring-rca/30"
            )}
          >
            <n.icon className="size-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">{n.title}</div>
              <div className="text-lg font-semibold tabular-nums">{n.value}</div>
              <div className="truncate text-xs text-muted-foreground">{n.detail}</div>
            </div>
          </div>
          {i < nodes.length - 1 && (
            <ArrowRight className="hidden size-4 shrink-0 text-muted-foreground xl:block" />
          )}
        </div>
      ))}
    </div>
  )
}
