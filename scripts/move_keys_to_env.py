"""Move API keys pasted into config/models.yaml into the git-ignored .env file.

For each provider whose api_key_env holds a key instead of a variable name, the key is
written to .env as OPENROUTER_API_KEY_<ROLE> and the config line is replaced with that name.
Prints only variable names, never key values.

    python scripts/move_keys_to_env.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "models.yaml"
ENV = ROOT / ".env"

role = None
lines_out, new_env = [], {}
for line in CONFIG.read_text().splitlines(keepends=True):
    m = re.match(r"^  (\w+):\s*$", line)
    if m:
        role = m.group(1)
    m = re.match(r"^(\s*api_key_env:\s*)(sk-\S+)\s*$", line)
    if m and role:
        name = f"OPENROUTER_API_KEY_{role.upper()}"
        if name in new_env and new_env[name] != m.group(2):
            raise SystemExit(f"two different keys for role {role}; fix config/models.yaml by hand")
        new_env[name] = m.group(2)
        line = f"{m.group(1)}{name}\n"
    lines_out.append(line)

if not new_env:
    raise SystemExit("no pasted keys found in config/models.yaml; nothing to do")

existing = ENV.read_text() if ENV.exists() else ""
kept = [l for l in existing.splitlines() if l.split("=", 1)[0].strip() not in new_env]
ENV.write_text("\n".join([*kept, *(f"{k}={v}" for k, v in new_env.items())]) + "\n")
ENV.chmod(0o600)
CONFIG.write_text("".join(lines_out))
print("moved keys into .env as: " + ", ".join(new_env))
