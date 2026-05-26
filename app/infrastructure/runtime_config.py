from __future__ import annotations

from PySide6.QtCore import QSettings

DATA_MODE_LOCAL = "local"
DATA_MODE_REMOTE = "remote"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def get_data_mode() -> str:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("data/mode", DATA_MODE_LOCAL)


def set_data_mode(mode: str) -> None:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("data/mode", mode)


def get_api_base_url() -> str:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("data/base_url", DEFAULT_API_BASE_URL)


def set_api_base_url(base_url: str) -> None:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("data/base_url", base_url)
