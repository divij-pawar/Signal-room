import { useEffect, useState } from "react"

import type { Bundle, Index } from "./types"

// Replay mode reads static bundles exported by the eval harness. A live-mode adapter
// (FastAPI) will expose the same shapes, so pages only ever use these hooks.

const base = `${import.meta.env.BASE_URL}demo-data/`
const cache = new Map<string, Promise<unknown>>()

function load<T>(file: string): Promise<T> {
  if (!cache.has(file)) {
    cache.set(
      file,
      fetch(base + file).then((r) => {
        if (!r.ok) throw new Error(`${file}: HTTP ${r.status}`)
        return r.json()
      })
    )
  }
  return cache.get(file) as Promise<T>
}

type State<T> = { data: T | null; error: string | null }

function useLoad<T>(file: string | null): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null })
  useEffect(() => {
    if (!file) return
    let live = true
    setState({ data: null, error: null })
    load<T>(file).then(
      (data) => live && setState({ data, error: null }),
      (e) => live && setState({ data: null, error: String(e) })
    )
    return () => {
      live = false
    }
  }, [file])
  return state
}

export const useIndex = () => useLoad<Index>("index.json")

export function useBundle(id: string | undefined) {
  return useLoad<Bundle>(id ? `${id}.json` : null)
}

export function useAllBundles(index: Index | null) {
  const [bundles, setBundles] = useState<Bundle[] | null>(null)
  useEffect(() => {
    if (!index) return
    Promise.all(index.scenarios.map((s) => load<Bundle>(s.file))).then(setBundles)
  }, [index])
  return bundles
}
