import { Link } from "react-router"

import { Loading, PageHeader } from "@/components/page"
import { Check, SeverityBadge } from "@/components/status"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAllBundles, useIndex } from "@/lib/data"
import { duration } from "@/lib/format"

export function IncidentsPage() {
  const { data: index, error } = useIndex()
  const bundles = useAllBundles(index)
  if (!index || !bundles) return <Loading error={error} />
  const incidents = bundles.filter((b) => b.incident)

  return (
    <>
      <PageHeader title="Incidents">
        Every escalation Guardian raised, with the RCA agent's verdict. Open one to see its evidence, the Slack message
        and the full tool-call audit.
      </PageHeader>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Root cause service</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Detected after</TableHead>
                <TableHead>Answer key</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {incidents.map((b) => {
                const inc = b.incident!
                return (
                  <TableRow key={b.scenario.id}>
                    <TableCell>
                      <Link className="font-medium underline-offset-4 hover:underline" to={`/incidents/${b.scenario.id}`}>
                        {b.scenario.title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <SeverityBadge severity={inc.report?.severity ?? inc.escalation.severity_guess} />
                    </TableCell>
                    <TableCell>{inc.report?.root_cause_service ?? <Badge variant="outline">no RCA</Badge>}</TableCell>
                    <TableCell>{inc.report?.confidence ?? "n/a"}</TableCell>
                    <TableCell>
                      {b.score.detection_latency_s != null ? duration(b.score.detection_latency_s) : "false alarm"}
                    </TableCell>
                    <TableCell>
                      {b.score.rca ? (
                        <Check ok={b.score.rca.service_correct} />
                      ) : (
                        <span className="text-muted-foreground">
                          {b.score.incident_detected == null ? "no fault in scenario" : "not scored"}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  )
}
