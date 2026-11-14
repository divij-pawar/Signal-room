import { lazy, Suspense } from "react"
import { HashRouter, Route, Routes } from "react-router"

import { AppShell } from "@/components/app-shell"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AboutPage } from "@/pages/about"
import { GuardrailsPage } from "@/pages/guardrails"
import { IncidentPage } from "@/pages/incident"
import { IncidentsPage } from "@/pages/incidents"
import { LabPage } from "@/pages/lab"
import { OverviewPage } from "@/pages/overview"
import { Loading } from "@/components/page"

// The charting library is only needed on the Evals page, so it loads on demand.
const EvalsPage = lazy(() => import("@/pages/evals").then((m) => ({ default: m.EvalsPage })))

// HashRouter: GitHub Pages serves static files only, so deep links must not need server rewrites.
export default function App() {
  return (
    <TooltipProvider delayDuration={150}>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="lab" element={<LabPage />} />
            <Route path="lab/:id" element={<LabPage />} />
            <Route path="incidents" element={<IncidentsPage />} />
            <Route path="incidents/:id" element={<IncidentPage />} />
            <Route path="guardrails" element={<GuardrailsPage />} />
            <Route
              path="evals"
              element={
                <Suspense fallback={<Loading />}>
                  <EvalsPage />
                </Suspense>
              }
            />
            <Route path="about" element={<AboutPage />} />
          </Route>
        </Routes>
      </HashRouter>
      <Toaster />
    </TooltipProvider>
  )
}
