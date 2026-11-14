import { useEffect, useMemo, useRef, useState } from "react"

import { ms } from "./format"
import type { Bundle } from "./types"

export const SPEEDS = [30, 60, 120, 300] as const

export type TimelineEvent = {
  t: number
  kind: "window" | "escalation" | "rca" | "slack" | "no-rca"
  index?: number
}

/**
 * Replays one bundle on a virtual clock. Guardian decides each window at its end; the RCA
 * report lands after its measured wall-clock latency; the Slack post follows the report.
 */
export function useReplay(bundle: Bundle) {
  const start = ms(bundle.scenario.start)
  const windowsEnd = start + bundle.scenario.windows * 240_000

  const events = useMemo<TimelineEvent[]>(() => {
    const ev: TimelineEvent[] = bundle.windows.map((w, index) => ({ t: ms(w.end), kind: "window", index }))
    const inc = bundle.incident
    if (inc) {
      const escAt = ms(inc.escalation.window_end)
      const rcaAt = escAt + Math.max(1, inc.rca_latency_s ?? 0) * 1000
      ev.push({ t: escAt, kind: "escalation" })
      if (inc.report) {
        ev.push({ t: rcaAt, kind: "rca" })
        if (inc.slack?.posted) ev.push({ t: rcaAt + 1000, kind: "slack" })
      } else {
        ev.push({ t: rcaAt, kind: "no-rca" })
      }
    }
    return ev.sort((a, b) => a.t - b.t)
  }, [bundle])

  const end = Math.max(windowsEnd, ...events.map((e) => e.t)) + 1000
  const [now, setNow] = useState(start)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<number>(60)
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!playing) return
    let frame = 0
    const tick = (wall: number) => {
      if (last.current != null) {
        const dt = (wall - last.current) * speed
        setNow((n) => {
          const next = Math.min(end, n + dt)
          if (next >= end) setPlaying(false)
          return next
        })
      }
      last.current = wall
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      last.current = null
    }
  }, [playing, speed, end])

  const visible = useMemo(() => events.filter((e) => e.t <= now), [events, now])

  return {
    start,
    end,
    now,
    playing,
    speed,
    events,
    visible,
    setSpeed,
    seek: (t: number) => setNow(Math.min(end, Math.max(start, t))),
    toggle: () => {
      if (now >= end) setNow(start)
      setPlaying((p) => !p)
    },
    restart: () => {
      setNow(start)
      setPlaying(false)
    },
    stepNext: () => {
      const next = events.find((e) => e.t > now)
      setPlaying(false)
      setNow(next ? next.t : end)
    },
    finish: () => {
      setPlaying(false)
      setNow(end)
    },
  }
}
