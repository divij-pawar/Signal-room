import type { PipelineCounts } from "@/components/pipeline-strip"
import type { Bundle } from "@/lib/types"

export function pipelineCounts(bundles: Bundle[]): PipelineCounts {
  const hosts = new Set(bundles.flatMap((b) => b.scenario.hosts)).size
  return {
    hosts: `${hosts}`,
    logs: bundles.reduce((n, b) => n + b.logs.length, 0),
    windows: bundles.reduce((n, b) => n + b.windows.length, 0),
    skipped: bundles.reduce((n, b) => n + b.windows.filter((w) => !w.model_called).length, 0),
    escalations: bundles.filter((b) => b.incident).length,
    reports: bundles.filter((b) => b.incident?.report).length,
    posts: bundles.filter((b) => b.incident?.slack?.posted).length,
  }
}
