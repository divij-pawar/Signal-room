import { CircleHelp, KeyRound, ShieldAlert, ShieldBan } from "lucide-react"

import { Loading, PageHeader, Stat } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAllBundles, useIndex } from "@/lib/data"
import { clock } from "@/lib/format"

export function GuardrailsPage() {
  const { data: index, error } = useIndex()
  const bundles = useAllBundles(index)
  if (!index || !bundles) return <Loading error={error} />

  const flagged = bundles.flatMap((b) =>
    b.guardrails.instruction_like_refs.map((ref) => ({ b, line: b.logs.find((l) => l.ref === ref)! }))
  )
  const redactions = bundles.reduce((n, b) => n + Object.values(b.guardrails.redactions).reduce((a, c) => a + c, 0), 0)
  const blocked = bundles.flatMap((b) => b.guardrails.blocked_tool_calls.map((a) => ({ b, a })))
  const gapWindows = bundles.flatMap((b) => b.windows.filter((w) => w.gold === "unknown"))

  return (
    <>
      <PageHeader title="Guardrails">
        Telemetry is untrusted. These are the checks that keep it from steering the agents, leaking secrets, or passing
        silence off as health.
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Instruction-like log lines" value={flagged.length} hint="Flagged and shown to models as data" />
        <Stat label="Secrets redacted" value={redactions} hint="Before any model call and before Slack" />
        <Stat label="Blocked tool calls" value={blocked.length} hint="Outside the RCA allowlist or bad arguments" />
        <Stat
          label="Missing-data windows reported OK"
          value={`${gapWindows.filter((w) => w.verdict === "ok").length} of ${gapWindows.length}`}
          hint="Must be 0"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="size-5 text-unknown" /> Prompt injection in logs
          </CardTitle>
          <CardDescription>
            Shown exactly as logged, as inert text. Agents receive these inside blocks marked untrusted and are told never
            to follow them.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {!flagged.length && <p className="text-sm text-muted-foreground">No instruction-like lines in these scenarios.</p>}
          {flagged.slice(0, 6).map(({ b, line }) => (
            <blockquote key={line.ref} className="rounded-md border-l-4 border-unknown bg-unknown/10 p-2 font-mono text-xs break-words whitespace-pre-wrap">
              {line.body}
              <div className="mt-1 font-sans text-muted-foreground">
                {b.scenario.title} · {line.service} · {clock(line.t)}
              </div>
            </blockquote>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Per scenario</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>
                  <KeyRound className="inline size-4" /> Secrets redacted
                </TableHead>
                <TableHead>Secret in raw RCA output</TableHead>
                <TableHead>
                  <ShieldBan className="inline size-4" /> Blocked calls
                </TableHead>
                <TableHead>
                  <CircleHelp className="inline size-4" /> No-data windows
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bundles.map((b) => {
                const gaps = b.windows.filter((w) => w.gold === "unknown")
                return (
                  <TableRow key={b.scenario.id}>
                    <TableCell className="font-medium">{b.scenario.title}</TableCell>
                    <TableCell>
                      {Object.entries(b.guardrails.redactions).map(([k, v]) => (
                        <Badge key={k} variant="secondary" className="mr-1">
                          {k.replace(/_/g, " ")} × {v}
                        </Badge>
                      )) ?? null}
                      {!Object.keys(b.guardrails.redactions).length && <span className="text-muted-foreground">none</span>}
                    </TableCell>
                    <TableCell>
                      {b.score.secret_leaks ? (
                        <span className="text-xs">
                          <Badge variant="outline" className="border-escalate/40 text-escalate">
                            yes
                          </Badge>{" "}
                          removed before Slack and from this replay
                        </span>
                      ) : (
                        <span className="text-muted-foreground">no</span>
                      )}
                    </TableCell>
                    <TableCell>{b.guardrails.blocked_tool_calls.length}</TableCell>
                    <TableCell>
                      {gaps.length ? `${gaps.filter((w) => w.verdict !== "ok").length}/${gaps.length} not reported OK` : "none"}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          <p className="mt-3 text-xs text-muted-foreground">
            "Secret in raw RCA output" counts planted secrets that appeared in the RCA agent's report before the Slack
            scrubber ran. The baseline RCA quotes logs verbatim, which is why the scrubber exists at the last step.
          </p>
        </CardContent>
      </Card>
    </>
  )
}
