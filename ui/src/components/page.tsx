import type { ReactNode } from "react"

import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
      {children && <p className="max-w-3xl text-sm text-muted-foreground">{children}</p>}
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
      </CardHeader>
      {hint && <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  )
}

export function Loading({ error }: { error?: string | null }) {
  if (error) return <p className="text-sm text-escalate">Could not load replay data: {error}</p>
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}
