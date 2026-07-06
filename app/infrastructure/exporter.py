from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_to_excel(rows: list[dict], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _FORMULA_PREFIXES = ("=", "+", "-", "@")
    sanitized = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES):
                clean[k] = "'" + v
            else:
                clean[k] = v
        sanitized.append(clean)
    df = pd.DataFrame(sanitized)
    df.to_excel(path, index=False)
