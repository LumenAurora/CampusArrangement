from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


def load_icon(name: str) -> QIcon:
    base_dir = Path(__file__).resolve().parent.parent / "resources" / "icons"
    path = base_dir / f"{name}.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon()
