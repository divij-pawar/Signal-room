import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

// A small theme provider. next-themes injects a <script> tag, which React 19 warns about in a
// client-only Vite app; this does the same job (class on <html>, follows the system setting).

type Theme = "light" | "dark" | "system"
type Ctx = { theme: Theme; resolvedTheme: "light" | "dark"; setTheme: (t: Theme) => void }

const ThemeContext = createContext<Ctx | null>(null)
const KEY = "signal-room-theme"
const media = () => window.matchMedia("(prefers-color-scheme: dark)")

function stored(): Theme {
  try {
    const t = localStorage.getItem(KEY)
    return t === "light" || t === "dark" ? t : "system"
  } catch {
    return "system"
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(stored)
  const [systemDark, setSystemDark] = useState(() => media().matches)

  useEffect(() => {
    const m = media()
    const onChange = () => setSystemDark(m.matches)
    m.addEventListener("change", onChange)
    return () => m.removeEventListener("change", onChange)
  }, [])

  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme
  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark")
    document.documentElement.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  const setTheme = (t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem(KEY, t)
    } catch {
      // Storage can be unavailable (private windows); the choice then lasts for this visit.
    }
  }

  return <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider")
  return ctx
}
