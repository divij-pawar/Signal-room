import type { Bundle, LogLine, Proportion } from "./types"

export const ms = (iso: string) => new Date(iso).getTime()

export const clock = (iso: string | number) => new Date(iso).toISOString().slice(11, 19)

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "n/a"
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  if (seconds < 90) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

export function pct(p: Proportion | null | undefined): string {
  if (!p || p.n === 0 || p.p == null) return "n/a"
  return `${(p.p * 100).toFixed(1)}%`
}

export function ci(p: Proportion | null | undefined): string {
  if (!p || p.n === 0 || p.ci95[0] == null || p.ci95[1] == null) return "no data"
  return `95% CI ${(p.ci95[0] * 100).toFixed(0)}–${(p.ci95[1] * 100).toFixed(0)}% · ${p.k}/${p.n}`
}

export const titleCase = (s: string) => s.replace(/[-_]/g, " ").replace(/^\w/, (c) => c.toUpperCase())

/** Evidence is verified only if the cited record exists and contains the excerpt verbatim. */
export function verifyEvidence(bundle: Bundle, ref: string, excerpt: string): LogLine | null {
  const line = bundle.logs.find((l) => l.ref === ref)
  return line && excerpt.trim() && line.body.includes(excerpt.trim()) ? line : null
}
