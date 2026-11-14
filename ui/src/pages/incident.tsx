import { useState } from "react"
import { CircleCheck, FlaskConical, ShieldX, TriangleAlert } from "lucide-react"
import { Link, useParams } from "react-router"

import { Loading, PageHeader, Stat } from "@/components/page"
import { Check, SeverityBadge, VerdictBadge } from "@/components/status"
import { WindowTimeline } from "@/components/window-timeline"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useBundle } from "@/lib/data"
import { clock, duration, ms, verifyEvidence } from "@/lib/format"
import type { Bundle } from "@/lib/types"

export function IncidentPage() {
  const { id } = useParams()
  const { data: b, error } = useBundle(id)
  const [reveal, setReveal] = useState(false)
  if (!b) return <Loading error={error} />
  const inc = b.incident
  if (!inc) {
    return (
      <PageHeader title={b.scenario.title}>
        Guardian did not escalate anything in this scenario, so there is no incident.
      </PageHeader>
    )
  }
  const report = inc.report
  const escAt = ms(inc.escalation.window_end)

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader title={b.scenario.title}>
          {b.scenario.family} · {b.scenario.difficulty}
          {b.scenario.synthetic && " · synthetic self-test"}
        </PageHeader>
        <Button asChild variant="outline">
          <Link to={`/lab/${b.scenario.id}`}>
            <FlaskConical /> Replay this scenario
          </Link>
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Severity" value={<SeverityBadge severity={report?.severity ?? inc.escalation.severity_guess} />} />
        <Stat
          label="Detected after"
          value={b.score.detection_latency_s != null ? duration(b.score.detection_latency_s) : "n/a"}
          hint="Fault start to escalation"
        />
        <Stat label="RCA took" value={duration(inc.rca_latency_s)} hint="Wall-clock time, measured" />
        <Stat
          label="Model calls"
          value={b.calls.length}
          hint={`${(b.score.tokens_in + b.score.tokens_out).toLocaleString()} tokens`}
        />
      </div>

      <Tabs defaultValue="report">
        <TabsList className="flex-wrap">
          <TabsTrigger value="report">Root cause</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="guardian">Guardian verdict</TabsTrigger>
          <TabsTrigger value="slack">Slack</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="report">
          <Card>
            <CardHeader>
              <CardTitle>{report ? `Root cause: ${report.root_cause_service}` : "No root cause report"}</CardTitle>
              <CardDescription>
                {report
                  ? `${report.root_cause_category} · ${report.confidence} confidence`
                  : `${inc.no_rca_reason ?? "The RCA stage failed"}. The escalation was still raised, flagged "no RCA".`}
              </CardDescription>
            </CardHeader>
            {report && (
              <CardContent className="flex flex-col gap-4 text-sm">
                <p className="whitespace-pre-wrap">{report.root_cause}</p>
                {report.next_steps.length > 0 && (
                  <div>
                    <div className="mb-1 font-medium">Next steps</div>
                    <ul className="list-disc pl-5">
                      {report.next_steps.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {report.unknowns.length > 0 && (
                  <Alert>
                    <TriangleAlert />
                    <AlertTitle>Unknowns</AlertTitle>
                    <AlertDescription>
                      <ul className="list-disc pl-5">
                        {report.unknowns.map((u) => (
                          <li key={u}>{u}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {report.affected_services.map((s) => (
                    <Badge key={s} variant="secondary">
                      {s}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            )}
          </Card>
          <AnswerKey bundle={b} reveal={reveal} setReveal={setReveal} />
        </TabsContent>

        <TabsContent value="evidence">
          <Card>
            <CardHeader>
              <CardTitle>Cited evidence</CardTitle>
              <CardDescription>
                Each excerpt is checked against the log line it cites. Unverifiable citations are removed by the agent's
                verifier and counted as hallucinations in the evals.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {!report?.evidence.length && <p className="text-sm text-muted-foreground">No evidence cited.</p>}
              {report?.evidence.map((e) => {
                const line = verifyEvidence(b, e.ref, e.excerpt)
                return (
                  <div key={e.ref + e.excerpt} className="rounded-md border p-3 text-sm">
                    <div className="mb-1 flex items-center gap-2">
                      {line ? (
                        <Badge variant="outline" className="border-ok/40 text-ok">
                          <CircleCheck /> verified
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="border-escalate/40 text-escalate">
                          <ShieldX /> not found in logs
                        </Badge>
                      )}
                      <span className="truncate font-mono text-xs text-muted-foreground">{e.ref}</span>
                    </div>
                    <p className="font-mono text-xs break-words whitespace-pre-wrap">“{e.excerpt}”</p>
                    {line && (
                      <p className="mt-1 font-mono text-xs break-words whitespace-pre-wrap text-muted-foreground">
                        {clock(line.t)} {line.service} {line.level} {line.body}
                      </p>
                    )}
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline">
          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <WindowTimeline windows={b.windows} showGold={reveal} />
              <ol className="relative flex flex-col gap-3 border-l pl-4 text-sm">
                {b.scenario.injection && reveal && (
                  <li>
                    <span className="font-mono text-xs text-muted-foreground">{clock(b.scenario.injection.start)}</span>{" "}
                    Fault injected (answer key): {b.scenario.injection.description}
                  </li>
                )}
                <li>
                  <span className="font-mono text-xs text-muted-foreground">{clock(escAt)}</span> Guardian escalated (
                  {inc.escalation.services.join(", ") || "no services named"})
                </li>
                <li>
                  <span className="font-mono text-xs text-muted-foreground">
                    {clock(escAt + (inc.rca_latency_s ?? 0) * 1000)}
                  </span>{" "}
                  {report ? `RCA report: ${report.root_cause_service}` : "RCA ended without a report"}
                </li>
                {inc.slack?.posted && (
                  <li>
                    <span className="font-mono text-xs text-muted-foreground">
                      {clock(escAt + (inc.rca_latency_s ?? 0) * 1000 + 1000)}
                    </span>{" "}
                    Posted to Slack
                  </li>
                )}
              </ol>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="guardian">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Escalated window <VerdictBadge verdict="escalate" />
              </CardTitle>
              <CardDescription>
                {clock(inc.escalation.window_start)}–{clock(inc.escalation.window_end)} · severity guess{" "}
                {inc.escalation.severity_guess}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <p>{inc.escalation.reason}</p>
              <div className="text-xs text-muted-foreground">
                Trace IDs: <span className="font-mono">{inc.escalation.trace_ids.join(", ") || "none"}</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="slack">
          <Card>
            <CardHeader>
              <CardTitle>Slack message</CardTitle>
              <CardDescription>
                {inc.slack
                  ? inc.slack.posted
                    ? "Posted to the one alert channel. Every field was secret-scrubbed first."
                    : "Below Sev 2, so not posted. Shown for reference."
                  : "No message: there was no RCA report."}
              </CardDescription>
            </CardHeader>
            {inc.slack && (
              <CardContent>
                <pre className="rounded-md bg-muted p-3 font-mono text-xs break-words whitespace-pre-wrap">
                  {inc.slack.text}
                </pre>
              </CardContent>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardHeader>
              <CardTitle>Tool-call audit</CardTitle>
              <CardDescription>
                Every tool the RCA agent asked for, allowed or blocked. The rule-based baseline makes no tool calls.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <AuditTable bundle={b} />
              <CallsTable bundle={b} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  )
}

function AnswerKey({ bundle: b, reveal, setReveal }: { bundle: Bundle; reveal: boolean; setReveal: (v: boolean) => void }) {
  const gt = b.ground_truth
  const rca = b.score.rca
  return (
    <Card className="mt-4">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Switch id="reveal" checked={reveal} onCheckedChange={setReveal} />
          <Label htmlFor="reveal">Reveal the answer key</Label>
        </div>
        <CardDescription>Hidden by default, so you can judge the report before seeing the truth.</CardDescription>
      </CardHeader>
      {reveal && (
        <CardContent className="grid gap-2 text-sm md:grid-cols-3">
          {gt.root_cause_service ? (
            <>
              <div>
                <div className="text-muted-foreground">True root cause</div>
                <div className="font-medium">
                  {gt.root_cause_service} ({gt.root_cause_category})
                </div>
                {rca && <Check ok={rca.service_correct} />}
              </div>
              <div>
                <div className="text-muted-foreground">True severity</div>
                <div className="font-medium">{gt.severity}</div>
                {rca && <Check ok={rca.severity_correct} />}
              </div>
              <div>
                <div className="text-muted-foreground">Evidence verified</div>
                <div className="font-medium">
                  {rca ? `${rca.evidence_verified} of ${rca.evidence_total}` : "n/a"}
                </div>
              </div>
            </>
          ) : (
            <div className="md:col-span-3">No fault was injected; any escalation here is a false alarm.</div>
          )}
          {b.scenario.traps.length > 0 && (
            <div className="md:col-span-3">
              <div className="text-muted-foreground">Traps in this scenario</div>
              <ul className="list-disc pl-5">
                {b.scenario.traps.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

function AuditTable({ bundle: b }: { bundle: Bundle }) {
  const audit = b.incident?.audit ?? []
  if (!audit.length) return <p className="text-sm text-muted-foreground">No tool calls recorded.</p>
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>#</TableHead>
          <TableHead>Tool</TableHead>
          <TableHead>Arguments</TableHead>
          <TableHead>Result</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {audit.map((a, i) => (
          <TableRow key={i}>
            <TableCell>{i + 1}</TableCell>
            <TableCell className="font-mono text-xs">{a.tool}</TableCell>
            <TableCell className="max-w-80 truncate font-mono text-xs">{JSON.stringify(a.arguments)}</TableCell>
            <TableCell>
              {a.allowed ? (
                <span className="text-xs">{a.result_summary}</span>
              ) : (
                <Badge variant="outline" className="border-escalate/40 text-escalate">
                  blocked: {a.result_summary}
                </Badge>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function CallsTable({ bundle: b }: { bundle: Bundle }) {
  if (!b.calls.length) return <p className="text-sm text-muted-foreground">No model calls in this run.</p>
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Role</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Tokens</TableHead>
          <TableHead className="text-right">Latency</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {b.calls.map((c, i) => (
          <TableRow key={i}>
            <TableCell>{c.role}</TableCell>
            <TableCell className="font-mono text-xs">{c.model}</TableCell>
            <TableCell>{c.ok ? "ok" : (c.error ?? c.status)}</TableCell>
            <TableCell className="text-right tabular-nums">{(c.tokens_in + c.tokens_out).toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums">{duration(c.latency_s)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
