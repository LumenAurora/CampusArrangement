from __future__ import annotations

import os
import unittest
from pathlib import Path

import PySide6
from PySide6.QtWidgets import QApplication

from app.ui.scheduling_widgets import _ActivityInfoCard, _StatCard
from app.ui.style import THEME_DARK, THEME_LIGHT, get_theme, set_theme
from app.ui.theme import DARK, LIGHT


class SchedulingPanelThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault(
            "QT_PLUGIN_PATH",
            str(Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"),
        )
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._old_theme = get_theme()
        self.addCleanup(lambda: set_theme(self._old_theme))

    def test_activity_info_card_refreshes_from_light_to_dark(self) -> None:
        set_theme(THEME_LIGHT)
        card = _ActivityInfoCard()
        self.assertIn(LIGHT.bg_card, card.styleSheet())

        set_theme(THEME_DARK)
        card.refresh_theme()

        self.assertIn(DARK.bg_card, card.styleSheet())
        self.assertNotIn(LIGHT.bg_card, card.styleSheet())

    def test_stat_card_refreshes_from_light_to_dark(self) -> None:
        set_theme(THEME_LIGHT)
        card = _StatCard("选项总数", "1", "accent")
        self.assertIn(LIGHT.bg_card, card.styleSheet())

        set_theme(THEME_DARK)
        card.refresh_theme()

        self.assertIn(DARK.bg_card, card.styleSheet())
        self.assertNotIn(LIGHT.bg_card, card.styleSheet())
