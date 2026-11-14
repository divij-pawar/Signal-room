"""Load KEY=VALUE pairs from a git-ignored .env file into the environment.

Keys never go in config files; config only names the environment variable to read.
Variables already set in the environment win over the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> list[str]:
    """Returns the names (never the values) of variables it set."""
    p = Path(path)
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        name, value = name.strip(), value.strip().strip("'\"")
        if name and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
