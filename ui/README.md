# Signal Room replay UI

A static console that replays recorded runs of the Signal Room eval pipeline: Overview,
Scenario lab, Incidents, Guardrails and Evals. Built with Vite, React, Tailwind and shadcn/ui.
Design: [docs/UI.md](../docs/UI.md).

```bash
npm install
npm run dev
```

The data in `public/demo-data/` is exported by the eval harness from the repository root:

```bash
.venv/bin/python -m signalroom.evals.export --split selftest --out ui/public/demo-data
```

Log bodies are secret-scrubbed during export, and the UI renders all telemetry as plain
text. Production builds ship a strict Content Security Policy. `VITE_BASE=/Signal-room/`
builds for the GitHub Pages project path; routing uses URL hashes so deep links work there.
