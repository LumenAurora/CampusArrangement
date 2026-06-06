from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_to_excel(rows: list[dict], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_excel(path, index=False)
