import { FlaskConical, Gauge, Info, LayoutDashboard, Moon, ShieldCheck, Siren, Sun } from "lucide-react"
import { useTheme } from "@/lib/theme"
import { NavLink, Outlet, useLocation } from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { useIndex } from "@/lib/data"

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/lab", label: "Scenario lab", icon: FlaskConical },
  { to: "/incidents", label: "Incidents", icon: Siren },
  { to: "/guardrails", label: "Guardrails", icon: ShieldCheck },
  { to: "/evals", label: "Evals", icon: Gauge },
  { to: "/about", label: "About", icon: Info },
]

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === "dark"
  return (
    <Button variant="ghost" size="icon" aria-label="Toggle dark mode" onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}

export function AppShell() {
  const { pathname } = useLocation()
  const { data: index } = useIndex()
  const current = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)))

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <div className="px-2 py-1">
            <div className="font-semibold">Signal Room</div>
            <div className="text-xs text-muted-foreground">Alert to root cause, fast</div>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((n) => (
                  <SidebarMenuItem key={n.to}>
                    <SidebarMenuButton asChild isActive={current?.to === n.to}>
                      <NavLink to={n.to}>
                        <n.icon />
                        <span>{n.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <div className="px-2 text-xs text-muted-foreground">
            {index
              ? `Guardian: ${index.agents.guardian} · RCA: ${index.agents.rca}`
              : "Loading replay data…"}
          </div>
        </SidebarFooter>
      </Sidebar>
      {/* min-w-0: let wide tables scroll inside the page instead of widening it */}
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-medium">{current?.label ?? "Signal Room"}</h1>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-6">
          <Alert>
            <AlertDescription>
              <span>
                <strong>Recorded replay, not live data.</strong> Every screen shows real output of the Signal Room eval
                pipeline, replayed on a clock.
                {index && !index.reportable && " These are synthetic self-test scenarios: not reportable results."}
              </span>
            </AlertDescription>
          </Alert>
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
