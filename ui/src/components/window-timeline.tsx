import { Bot, Zap } from "lucide-react"

import { VERDICT } from "@/components/status"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { clock, ms } from "@/lib/format"
import type { WindowVerdict } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Guardian's 4-minute windows. Undecided windows (still in the future on the replay clock) are dimmed. */
export function WindowTimeline({
  windows,
  now,
  showGold = false,
  compact = false,
}: {
  windows: WindowVerdict[]
  now?: number
  showGold?: boolean
  compact?: boolean
}) {
  return (
    <div className="flex gap-1" role="list" aria-label="Guardian windows">
      {windows.map((w) => {
        const decided = now == null || ms(w.end) <= now
        const active = now != null && ms(w.start) <= now && now < ms(w.end)
        const v = VERDICT[w.verdict]
        return (
          <Tooltip key={w.start}>
            <TooltipTrigger asChild>
              <div
                role="listitem"
                className={cn(
                  "flex flex-1 flex-col items-center justify-center rounded-md border text-xs transition-opacity",
                  compact ? "h-7" : "h-14 gap-0.5",
                  decided ? [v.bg, v.border, v.text] : "border-dashed opacity-50",
                  active && "ring-2 ring-ring",
                  showGold && decided && !w.correct && "outline-2 outline-offset-1 outline-escalate"
                )}
              >
                {decided ? <v.icon className="size-4" /> : <span className="text-muted-foreground">…</span>}
                {!compact && (
                  <span className="text-[10px] text-muted-foreground">{clock(w.start).slice(0, 5)}</span>
                )}
              </div>
            </TooltipTrigger>
            <TooltipContent className="max-w-72">
              <div className="font-medium">
                {clock(w.start)}–{clock(w.end)} · {decided ? v.label : "not decided yet"}
              </div>
              {decided && (
                <>
                  <div className="mt-1">{w.reason}</div>
                  <div className="mt-1 flex items-center gap-1 opacity-80">
                    {w.model_called ? <Bot className="size-3" /> : <Zap className="size-3" />}
                    {w.model_called ? "Model called" : "Decided by cheap signals, no model call"} · hosts{" "}
                    {w.hosts_reporting}/{w.hosts_expected}
                  </div>
                  {showGold && (
                    <div className="mt-1 opacity-80">
                      Expected: {VERDICT[w.gold].label} · {w.correct ? "correct" : "wrong"}
                    </div>
                  )}
                </>
              )}
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
