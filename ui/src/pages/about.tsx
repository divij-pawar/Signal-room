import { PageHeader } from "@/components/page"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const REPO = "https://github.com/divij-pawar/Signal-room"

export function AboutPage() {
  return (
    <>
      <PageHeader title="About Signal Room">
        A two-tier incident-response agent: a small model triages telemetry every 4 minutes, and a stronger model finds
        the root cause of each escalation, citing the log lines it relied on.
      </PageHeader>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Claims policy</CardTitle>
            <CardDescription>How to read every number in this app</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <ul className="list-disc space-y-1 pl-5">
              <li>Every number comes from a recorded eval run, replayed here unchanged.</li>
              <li>Synthetic self-test scenarios check the harness; they are never reported as results.</li>
              <li>Small samples are shown with their confidence intervals, not as bare percentages.</li>
              <li>Costs are estimates from token counts and published per-token prices.</li>
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Guardrails</CardTitle>
            <CardDescription>Built into the pipeline, measured by the evals</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <ul className="list-disc space-y-1 pl-5">
              <li>Telemetry is data, never instructions.</li>
              <li>The RCA agent can call only four read-only tools; anything else is blocked and audited.</li>
              <li>Secrets are scrubbed before every model call and before Slack.</li>
              <li>Missing data is reported as unknown, never as healthy.</li>
            </ul>
          </CardContent>
        </Card>
      </div>
      <p className="text-sm text-muted-foreground">
        Source, design docs and evaluation plan:{" "}
        <a className="underline underline-offset-4" href={REPO} target="_blank" rel="noreferrer">
          {REPO.replace("https://", "")}
        </a>
      </p>
    </>
  )
}
