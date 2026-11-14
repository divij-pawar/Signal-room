import { useEffect, useMemo, useRef } from "react"
import { ShieldAlert, ShieldCheck } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { clock, ms } from "@/lib/format"
import type { LogLine } from "@/lib/types"
import { cn } from "@/lib/utils"

const LEVEL = { ERROR: "text-escalate", WARN: "text-unknown", INFO: "text-muted-foreground" }

/**
 * Raw telemetry as plain text. Bodies are rendered as React text nodes (escaped), never as
 * HTML or Markdown: log content is untrusted and must stay inert in the UI too.
 */
export function LogStream({
  logs,
  now,
  flagged,
  highlight,
  onlyProblems = false,
  max = 250,
  className,
}: {
  logs: LogLine[]
  now?: number
  flagged: Set<string>
  highlight?: Set<string>
  onlyProblems?: boolean
  max?: number
  className?: string
}) {
  const shown = useMemo(() => {
    const visible = logs.filter(
      (l) => (now == null || ms(l.t) <= now) && (!onlyProblems || l.level !== "INFO" || flagged.has(l.ref))
    )
    return visible.slice(-max)
  }, [logs, now, onlyProblems, flagged, max])

  // Follow the newest line by scrolling this container only, never the page.
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (now != null && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [shown.length, now])

  return (
    <div ref={box} className={cn("overflow-auto font-mono text-xs leading-relaxed", className)}>
      {!shown.length && <p className="p-4 font-sans text-sm text-muted-foreground">No log lines yet. Press play.</p>}
      {shown.map((l) => (
        <div
          key={l.ref}
          className={cn(
            "border-l-2 border-transparent px-2 py-0.5 break-words whitespace-pre-wrap",
            flagged.has(l.ref) && "border-unknown bg-unknown/10",
            highlight?.has(l.ref) && "border-rca bg-rca/10"
          )}
        >
          {/* Inline metadata, so on narrow screens the message wraps underneath instead of into a sliver. */}
          <span className="text-muted-foreground">{clock(l.t)} </span>
          <span className="inline-block w-28 truncate align-bottom text-muted-foreground">{l.service}</span>
          <span className={cn("inline-block w-12", LEVEL[l.level])}>{l.level}</span>
          <span>
            {l.body}
            {l.redacted && (
              <Badge variant="outline" className="ml-2 h-4 px-1 text-[10px]">
                <ShieldCheck /> secret redacted
              </Badge>
            )}
            {flagged.has(l.ref) && (
              <Badge variant="outline" className="ml-2 h-4 border-unknown/50 px-1 text-[10px] text-unknown">
                <ShieldAlert /> instruction-like text, treated as data
              </Badge>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}
