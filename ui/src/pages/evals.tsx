import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { Loading, PageHeader, Stat } from "@/components/page"
import { Check } from "@/components/status"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAllBundles, useIndex } from "@/lib/data"
import { ci, duration, pct } from "@/lib/format"

const LABELS = ["ok", "escalate", "unknown"] as const

const chartConfig = {
  correct: { label: "Correct windows", color: "var(--ok)" },
  wrong: { label: "Wrong windows", color: "var(--escalate)" },
} satisfies ChartConfig

export function EvalsPage() {
  const { data: index, error } = useIndex()
  const bundles = useAllBundles(index)
  if (!index || !bundles) return <Loading error={error} />
  const s = index.summary
  const chartData = bundles.map((b) => ({
    scenario: b.scenario.id.replace("selftest-", ""),
    correct: b.windows.filter((w) => w.correct).length,
    wrong: b.windows.filter((w) => !w.correct).length,
  }))

  return (
    <>
      <PageHeader title="Evals">
        Mechanical scoring against each scenario's answer key, with 95% Wilson intervals. Small samples give wide
        intervals; they are shown on purpose.
      </PageHeader>

      {!index.reportable && (
        <Alert>
          <AlertDescription>
            These numbers come from synthetic self-test scenarios that check the harness itself. They are not results
            about Signal Room's accuracy. Agents: {index.agents.guardian} Guardian, {index.agents.rca} RCA.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Window accuracy" value={pct(s.window_accuracy)} hint={ci(s.window_accuracy)} />
        <Stat label="Incident recall" value={pct(s.incident_recall)} hint={ci(s.incident_recall)} />
        <Stat label="False escalations" value={pct(s.false_escalation_rate)} hint={ci(s.false_escalation_rate)} />
        <Stat label="Detection latency" value={duration(s.detection_latency_median_s)} hint="Median" />
        <Stat label="RCA root cause (top-1)" value={pct(s.rca_service_top1)} hint={ci(s.rca_service_top1)} />
        <Stat label="RCA category" value={pct(s.rca_category)} hint={ci(s.rca_category)} />
        <Stat label="Evidence faithfulness" value={pct(s.evidence_faithfulness)} hint={ci(s.evidence_faithfulness)} />
        <Stat label="Secret leaks (raw RCA)" value={s.secret_leaks} hint="Before the Slack scrubber" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Guardian windows by scenario</CardTitle>
            <CardDescription>Correct vs. wrong 4-minute verdicts</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-64 w-full">
              <BarChart data={chartData} accessibilityLayer>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="scenario" tickLine={false} axisLine={false} fontSize={11} />
                <YAxis allowDecimals={false} width={24} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="correct" stackId="a" fill="var(--color-correct)" radius={[0, 0, 4, 4]} />
                <Bar dataKey="wrong" stackId="a" fill="var(--color-wrong)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Confusion matrix</CardTitle>
            <CardDescription>Rows: expected verdict. Columns: Guardian's verdict.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Expected ↓ / Got →</TableHead>
                  {LABELS.map((l) => (
                    <TableHead key={l} className="text-right">
                      {l}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {LABELS.map((gold) => (
                  <TableRow key={gold}>
                    <TableCell className="font-medium">{gold}</TableCell>
                    {LABELS.map((pred) => {
                      const n = s.confusion[`${gold}->${pred}`] ?? 0
                      return (
                        <TableCell
                          key={pred}
                          className={`text-right tabular-nums ${gold === pred ? "font-semibold text-ok" : n ? "text-escalate" : "text-muted-foreground"}`}
                        >
                          {n}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
              <div className="text-muted-foreground">Model calls</div>
              <div className="tabular-nums">{s.model_calls}</div>
              <div className="text-muted-foreground">Windows without a model call</div>
              <div className="tabular-nums">{pct(s.guardian_windows_without_model_call)}</div>
              <div className="text-muted-foreground">Tokens per incident</div>
              <div className="tabular-nums">{s.tokens_per_incident_mean?.toFixed(0) ?? "n/a"}</div>
              <div className="text-muted-foreground">Estimated cost</div>
              <div className="tabular-nums">${s.cost_usd_estimate.toFixed(4)}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Per scenario</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Windows correct</TableHead>
                <TableHead>Detected</TableHead>
                <TableHead>Root cause</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Evidence verified</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bundles.map((b) => (
                <TableRow key={b.scenario.id}>
                  <TableCell className="font-medium">{b.scenario.title}</TableCell>
                  <TableCell className="tabular-nums">
                    {b.windows.filter((w) => w.correct).length}/{b.windows.length}
                  </TableCell>
                  <TableCell>
                    {b.score.incident_detected == null ? (
                      <span className="text-muted-foreground">no fault</span>
                    ) : (
                      <Check ok={b.score.incident_detected} label={b.score.incident_detected ? "Yes" : "Missed"} />
                    )}
                  </TableCell>
                  <TableCell>
                    <Check ok={b.score.rca?.service_correct} />
                  </TableCell>
                  <TableCell>
                    <Check ok={b.score.rca?.category_correct} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {b.score.rca ? `${b.score.rca.evidence_verified}/${b.score.rca.evidence_total}` : "n/a"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  )
}
