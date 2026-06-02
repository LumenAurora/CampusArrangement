from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ICON_DASHBOARD = "dashboard"
ICON_ACTIVITIES = "activities"
ICON_SCHEDULING = "scheduling"
ICON_USERS = "users"
ICON_SIGNUP = "signup"
ICON_RESULTS = "results"
ICON_CHECKIN = "checkin"

ICON_NAMES = frozenset({
    ICON_DASHBOARD,
    ICON_ACTIVITIES,
    ICON_SCHEDULING,
    ICON_USERS,
    ICON_SIGNUP,
    ICON_RESULTS,
    ICON_CHECKIN,
})


def load_icon(name: str) -> QIcon:
    base_dir = Path(__file__).resolve().parent.parent / "resources" / "icons"
    path = base_dir / f"{name}.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon()
