import { useMemo, useState } from "react"
import { ArrowRight, Bot, FastForward, MessageSquare, Pause, Play, RotateCcw, SkipForward, Siren, Zap } from "lucide-react"
import { Link, useNavigate, useParams } from "react-router"

import { LogStream } from "@/components/log-stream"
import { Loading, PageHeader } from "@/components/page"
import { PipelineStrip } from "@/components/pipeline-strip"
import { SeverityBadge, VERDICT, VerdictBadge } from "@/components/status"
import { WindowTimeline } from "@/components/window-timeline"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useBundle, useIndex } from "@/lib/data"
import { clock, duration, ms } from "@/lib/format"
import { SPEEDS, useReplay } from "@/lib/replay"
import type { Bundle } from "@/lib/types"
import { cn } from "@/lib/utils"

export function LabPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: index, error } = useIndex()
  const scenarioId = id ?? index?.scenarios[0]?.id
  const { data: bundle, error: bundleError } = useBundle(scenarioId)

  if (!index) return <Loading error={error} />

  return (
    <>
      <PageHeader title="Scenario lab">
        Replay a recorded scenario. Raw logs scroll on the left; Guardian, the RCA agent and Slack react on the right as
        the clock passes each 4-minute window.
      </PageHeader>
      <Select value={scenarioId} onValueChange={(v) => navigate(`/lab/${v}`)}>
        <SelectTrigger className="w-full md:w-96" aria-label="Scenario">
          <SelectValue placeholder="Pick a scenario" />
        </SelectTrigger>
        <SelectContent>
          {index.scenarios.map((s) => (
            <SelectItem key={s.id} value={s.id}>
              {s.title} · {s.family}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {bundle && bundle.scenario.id === scenarioId ? (
        <Player key={bundle.scenario.id} bundle={bundle} />
      ) : (
        <Loading error={bundleError} />
      )}
    </>
  )
}

function Player({ bundle }: { bundle: Bundle }) {
  const r = useReplay(bundle)
  const [onlyProblems, setOnlyProblems] = useState(false)
  const flagged = useMemo(() => new Set(bundle.guardrails.instruction_like_refs), [bundle])
  const evidence = useMemo(
    () => new Set(bundle.incident?.report?.evidence.map((e) => e.ref) ?? []),
    [bundle]
  )
  const seen = (kind: string) => r.visible.some((e) => e.kind === kind)
  const decided = bundle.windows.filter((w) => ms(w.end) <= r.now)
  const counts = {
    hosts: `${bundle.scenario.hosts.length}`,
    logs: bundle.logs.filter((l) => ms(l.t) <= r.now).length,
    windows: decided.length,
    skipped: decided.filter((w) => !w.model_called).length,
    escalations: seen("escalation") ? 1 : 0,
    reports: seen("rca") ? 1 : 0,
    posts: seen("slack") ? 1 : 0,
  }
  const done = r.now >= r.end

  return (
    <div className="flex flex-col gap-4">
      <Card size="sm">
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={r.toggle} aria-label={r.playing ? "Pause" : "Play"}>
              {r.playing ? <Pause /> : <Play />}
              {r.playing ? "Pause" : done ? "Replay" : "Play"}
            </Button>
            <Button variant="outline" onClick={r.stepNext} disabled={done}>
              <SkipForward /> Next event
            </Button>
            <Button variant="outline" onClick={r.finish} disabled={done}>
              <FastForward /> Skip to end
            </Button>
            <Button variant="ghost" size="icon" onClick={r.restart} aria-label="Restart">
              <RotateCcw />
            </Button>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={String(r.speed)}
              onValueChange={(v) => v && r.setSpeed(Number(v))}
              aria-label="Playback speed"
            >
              {SPEEDS.map((s) => (
                <ToggleGroupItem key={s} value={String(s)}>
                  {s}×
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <span className="ml-auto font-mono text-sm tabular-nums">{clock(r.now)} UTC</span>
          </div>
          <Slider
            value={[r.now]}
            min={r.start}
            max={r.end}
            step={1000}
            onValueChange={([v]) => r.seek(v)}
            aria-label="Replay position"
          />
          <WindowTimeline windows={bundle.windows} now={r.now} />
        </CardContent>
      </Card>

      <PipelineStrip counts={counts} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Raw telemetry</CardTitle>
            <CardDescription>
              Untrusted input, shown as plain text. Secrets were scrubbed before this replay was exported.
            </CardDescription>
            <div className="flex items-center gap-2 pt-1">
              <Switch id="problems" checked={onlyProblems} onCheckedChange={setOnlyProblems} />
              <Label htmlFor="problems" className="text-xs">
                Errors, warnings and flagged lines only
              </Label>
            </div>
          </CardHeader>
          <CardContent>
            <LogStream
              logs={bundle.logs}
              now={r.now}
              flagged={flagged}
              highlight={seen("rca") ? evidence : undefined}
              onlyProblems={onlyProblems}
              className="h-[480px] rounded-md border"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What Signal Room did</CardTitle>
            <CardDescription>Decisions appear when they were made on the replay clock.</CardDescription>
          </CardHeader>
          <CardContent className="flex h-[528px] flex-col gap-2 overflow-auto">
            {!r.visible.length && <p className="text-sm text-muted-foreground">Nothing decided yet. Press play.</p>}
            {r.visible.map((e) => (
              <Event key={`${e.kind}-${e.index ?? 0}`} bundle={bundle} kind={e.kind} index={e.index} />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Event({ bundle, kind, index }: { bundle: Bundle; kind: string; index?: number }) {
  const inc = bundle.incident
  if (kind === "window" && index != null) {
    const w = bundle.windows[index]
    return (
      <div className={cn("rounded-md border-l-4 bg-muted/40 p-2 text-sm", VERDICT[w.verdict].border)}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{clock(w.end)}</span>
          <span className="font-medium">Guardian</span>
          <VerdictBadge verdict={w.verdict} />
          <Badge variant="outline" className="text-muted-foreground">
            {w.model_called ? <Bot /> : <Zap />}
            {w.model_called ? "model called" : "no model call"}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{w.reason}</p>
      </div>
    )
  }
  if (!inc) return null
  if (kind === "escalation") {
    return (
      <div className="rounded-md border-l-4 border-escalate bg-escalate/10 p-2 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <Siren className="size-4 text-escalate" /> Escalation queued
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Services: {inc.escalation.services.join(", ") || "none named"} · dedupe key{" "}
          <span className="font-mono">{inc.escalation.dedupe_key.slice(0, 40)}</span>
        </p>
      </div>
    )
  }
  if (kind === "no-rca") {
    return (
      <div className="rounded-md border-l-4 border-unknown bg-unknown/10 p-2 text-sm">
        <span className="font-medium">No RCA report</span>
        <p className="mt-1 text-xs text-muted-foreground">
          {inc.no_rca_reason ?? "The RCA stage did not produce a report"}. The escalation still stands, flagged "no RCA".
        </p>
      </div>
    )
  }
  if (kind === "rca" && inc.report) {
    return (
      <div className="rounded-md border-l-4 border-rca bg-rca/10 p-2 text-sm">
        <div className="flex flex-wrap items-center gap-2 font-medium">
          <Bot className="size-4 text-rca" /> Root cause report
          <SeverityBadge severity={inc.report.severity} />
          <Badge variant="outline">{inc.report.confidence} confidence</Badge>
          <span className="text-xs font-normal text-muted-foreground">after {duration(inc.rca_latency_s)}</span>
        </div>
        <p className="mt-1">
          <span className="font-medium">{inc.report.root_cause_service}</span> ({inc.report.root_cause_category}):{" "}
          {inc.report.root_cause}
        </p>
        <Button asChild variant="link" size="sm" className="h-auto px-0">
          <Link to={`/incidents/${bundle.scenario.id}`}>
            Open the incident <ArrowRight />
          </Link>
        </Button>
      </div>
    )
  }
  if (kind === "slack" && inc.slack) {
    return (
      <div className="rounded-md border-l-4 border-primary/40 bg-muted/40 p-2 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <MessageSquare className="size-4" /> Posted to Slack
        </div>
        <pre className="mt-1 font-mono text-xs break-words whitespace-pre-wrap text-muted-foreground">{inc.slack.text}</pre>
      </div>
    )
  }
  return null
}
