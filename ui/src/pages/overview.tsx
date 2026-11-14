import { ArrowRight, FlaskConical } from "lucide-react"
import { Link } from "react-router"

import { Loading, PageHeader, Stat } from "@/components/page"
import { PipelineStrip } from "@/components/pipeline-strip"
import { Check, SeverityBadge } from "@/components/status"
import { WindowTimeline } from "@/components/window-timeline"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { useAllBundles, useIndex } from "@/lib/data"
import { pipelineCounts } from "@/lib/pipeline"
import { ci, duration, pct, titleCase } from "@/lib/format"

const STEPS = [
  ["Watchers stream logs", "Each host ships its logs over OTLP to the telemetry server."],
  ["Guardian triages 4-minute windows", "Drain3 condenses each window; cheap signals decide if a model is needed at all."],
  ["Escalations become queued jobs", "One durable job per incident, de-duplicated by trace."],
  ["The RCA agent investigates", "Read-only, allowlisted tools; every citation is checked against real log lines."],
  ["Slack gets the root cause", "Sev 1 and 2 only, one channel, secrets scrubbed at the last step."],
]

export function OverviewPage() {
  const { data: index, error } = useIndex()
  const bundles = useAllBundles(index)
  if (!index || !bundles) return <Loading error={error} />
  const s = index.summary

  return (
    <>
      <PageHeader title="From alert to root cause">
        Signal Room watches telemetry, triages it in 4-minute windows with a small model, and hands real incidents to
        a root cause agent that cites its evidence. This replay shows {index.scenarios.length} recorded scenarios.
      </PageHeader>

      <PipelineStrip counts={pipelineCounts(bundles)} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Incidents detected" value={pct(s.incident_recall)} hint={ci(s.incident_recall)} />
        <Stat
          label="Detection latency (median)"
          value={duration(s.detection_latency_median_s)}
          hint="Fault start to first escalation"
        />
        <Stat label="RCA root cause correct" value={pct(s.rca_service_top1)} hint={ci(s.rca_service_top1)} />
        <Stat
          label="Missing data reported as OK"
          value={pct(s.missing_data_reported_ok)}
          hint="Must stay at 0: no data is not healthy"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>How it works</CardTitle>
          <CardDescription>The same five stages run in every scenario below.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 md:grid-cols-5">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="flex flex-col gap-1">
                <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
                  {i + 1}
                </span>
                <span className="text-sm font-medium">{title}</span>
                <span className="text-xs text-muted-foreground">{text}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3">
        <h3 className="text-lg font-semibold">Scenarios</h3>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {bundles.map((b) => {
            const inc = b.incident
            return (
              <Card key={b.scenario.id}>
                <CardHeader>
                  <CardTitle>{b.scenario.title}</CardTitle>
                  <CardDescription className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary">{titleCase(b.scenario.family)}</Badge>
                    <Badge variant="outline">{b.scenario.difficulty}</Badge>
                    {b.scenario.synthetic && <Badge variant="outline">synthetic</Badge>}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <WindowTimeline windows={b.windows} compact showGold />
                  <div className="text-sm">
                    {inc ? (
                      <div className="flex flex-col gap-1">
                        <span className="flex items-center gap-2">
                          <SeverityBadge severity={inc.report?.severity ?? inc.escalation.severity_guess} />
                          {inc.report ? `Blamed ${inc.report.root_cause_service}` : "No RCA report"}
                        </span>
                        {b.score.rca && <Check ok={b.score.rca.service_correct} label={b.score.rca.service_correct ? "Matches the answer key" : "Does not match the answer key"} />}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">No escalation</span>
                    )}
                  </div>
                </CardContent>
                <CardFooter className="gap-2">
                  <Button asChild size="sm">
                    <Link to={`/lab/${b.scenario.id}`}>
                      <FlaskConical /> Replay
                    </Link>
                  </Button>
                  {inc && (
                    <Button asChild size="sm" variant="outline">
                      <Link to={`/incidents/${b.scenario.id}`}>
                        Incident <ArrowRight />
                      </Link>
                    </Button>
                  )}
                </CardFooter>
              </Card>
            )
          })}
        </div>
      </div>
    </>
  )
}
