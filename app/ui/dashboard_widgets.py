from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.domain.models import ActivityStatus, User
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
)
from app.ui.style import get_palette
from app.ui.ui_utils import format_activity_status


class DashboardPanel(QWidget):
    def __init__(
        self,
        user: User,
        activity_repo: ActivityRepository,
        slot_repo: TimeSlotRepository,
        reg_repo: RegistrationRepository,
        schedule_repo: ScheduleRepository,
    ) -> None:
        super().__init__()
        self._user = user
        self._activity_repo = activity_repo
        self._slot_repo = slot_repo
        self._reg_repo = reg_repo
        self._schedule_repo = schedule_repo

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        header = QLabel("概览")
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        desc = QLabel("关键指标与最新动态")
        desc.setObjectName("pageSubtitle")
        layout.addWidget(desc)

        layout.addSpacing(8)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        layout.addLayout(self._grid)

        self._section_container = QVBoxLayout()
        self._section_container.setSpacing(24)
        layout.addLayout(self._section_container)

        layout.addStretch(1)
        self.setLayout(layout)

        self.refresh()

    # ── data helpers ──────────────────────────────────────────

    def _is_admin(self) -> bool:
        return self._user.role.value in {"super_admin", "organizer"}

    def _stat_cards_data(self) -> list[tuple[str, int, str]]:
        """Return (label, value, accent_color_key) tuples."""
        p = get_palette()
        if self._is_admin():
            return [
                ("活动总数", self._activity_repo.count_all(), "accent"),
                ("时段总数", self._slot_repo.count_all(), "success_fg"),
                ("报名总数", self._reg_repo.count_all(), "warning_fg"),
                ("排班结果", self._schedule_repo.count_all(), "error_fg"),
            ]
        return [
            ("可报名活动", self._activity_repo.count_by_status(ActivityStatus.OPEN), "accent"),
            ("我的报名", self._reg_repo.count_by_user(self._user.id), "success_fg"),
            ("我的排班", self._schedule_repo.count_by_user(self._user.id), "warning_fg"),
            ("已发布时段", self._slot_repo.count_by_activity_status(ActivityStatus.OPEN.value), "error_fg"),
        ]

    def _recent_activities(self) -> list[dict]:
        """Latest 5 activities with status info."""
        if self._is_admin():
            rows = self._activity_repo.list_all()
        else:
            rows = self._activity_repo.list_by_status(ActivityStatus.OPEN)
        return rows[:5]

    def _recent_registrations_count(self) -> int:
        """For admin/organizer: count of registrations in the last 7 days."""
        return self._reg_repo.count_all()

    def _upcoming_schedules(self) -> list[dict]:
        """For regular users: next 3 schedule results with slot info."""
        rows = self._schedule_repo.list_by_user(self._user.id)
        now = datetime.now().isoformat()
        upcoming = []
        for row in rows:
            slot = self._slot_repo.get(row.get("slot_id", ""))
            if slot:
                end = slot.get("end_time", "")
                if end and end >= now:
                    upcoming.append({**row, "_slot": slot})
        upcoming.sort(key=lambda r: r["_slot"].get("start_time", ""))
        return upcoming[:3]

    # ── build / refresh ───────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_stat_cards()
        self._refresh_sections()

    def _clear_layout(self, layout: QVBoxLayout | QGridLayout) -> None:
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

    def _refresh_stat_cards(self) -> None:
        self._clear_layout(self._grid)
        p = get_palette()
        for index, (label, value, color_key) in enumerate(self._stat_cards_data()):
            color = getattr(p, color_key, p.accent)
            card = _StatCard(label, value, color)
            row, col = divmod(index, 2)
            self._grid.addWidget(card, row, col)

    def _refresh_sections(self) -> None:
        self._clear_layout(self._section_container)
        p = get_palette()

        # ── Recent Activities ─────────────────────────────────
        recent = self._recent_activities()
        if recent:
            section = self._build_recent_activities_section(recent, p)
            self._section_container.addWidget(section)

        # ── Admin: recent registrations count ─────────────────
        if self._is_admin():
            reg_count = self._recent_registrations_count()
            reg_section = self._build_registrations_summary(reg_count, p)
            self._section_container.addWidget(reg_section)

        # ── Regular user: upcoming schedules ──────────────────
        if not self._is_admin():
            upcoming = self._upcoming_schedules()
            sched_section = self._build_upcoming_schedules_section(upcoming, p)
            self._section_container.addWidget(sched_section)

    # ── section builders ──────────────────────────────────────

    def _build_recent_activities_section(self, activities: list[dict], p) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sectionFrame")
        frame.setStyleSheet(f"""
            QFrame#sectionFrame {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout()
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QLabel("最近活动")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text_primary}; border: none;")
        lay.addWidget(title)

        status_colors = {
            "open": p.success_fg,
            "draft": p.text_tertiary,
            "pending_review": p.warning_fg,
            "closed": p.text_secondary,
            "archived": p.text_tertiary,
            "签到未开始": p.accent,
            "签到中": p.success_fg,
            "签到已结束": p.error_fg,
            "报名未开始": p.accent,
            "报名已截止": p.error_fg,
        }

        for act in activities:
            row_frame = QFrame()
            status_val = act.get("status", "draft")
            status_text = format_activity_status(act)
            color = (
                status_colors.get(status_text)
                if status_text in status_colors
                else status_colors.get(status_val, p.text_tertiary)
            )
            row_frame.setStyleSheet(f"""
                QFrame {{
                    background: {p.bg_input};
                    border-left: 3px solid {color};
                    border-radius: 6px;
                    padding: 2px 0;
                }}
            """)
            row_lay = QHBoxLayout()
            row_lay.setContentsMargins(10, 6, 8, 6)
            row_lay.setSpacing(8)

            name = QLabel(act.get("name", "—"))
            name.setStyleSheet(f"color: {p.text_primary}; font-weight: 500; border: none;")
            row_lay.addWidget(name)

            row_lay.addStretch(1)

            status_text = format_activity_status(act)
            badge = QLabel(status_text)
            badge.setStyleSheet(f"""
                color: {color};
                background: {p.bg_card};
                border: 1px solid {color};
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 500;
            """)
            row_lay.addWidget(badge)

            signup_start = act.get("signup_start", "")
            if signup_start:
                try:
                    dt = datetime.fromisoformat(signup_start)
                    time_label = QLabel(dt.strftime("%m-%d %H:%M"))
                except (ValueError, TypeError):
                    time_label = QLabel("")
            else:
                time_label = QLabel("")
            time_label.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
            row_lay.addWidget(time_label)

            row_frame.setLayout(row_lay)
            lay.addWidget(row_frame)

        frame.setLayout(lay)
        return frame

    def _build_registrations_summary(self, count: int, p) -> QFrame:
        frame = QFrame()
        frame.setObjectName("regSummaryFrame")
        frame.setStyleSheet(f"""
            QFrame#regSummaryFrame {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-radius: 16px;
            }}
        """)
        lay = QHBoxLayout()
        lay.setContentsMargins(20, 14, 20, 14)

        icon_bar = QFrame()
        icon_bar.setFixedWidth(4)
        icon_bar.setStyleSheet(f"background: {p.accent}; border-radius: 2px;")
        lay.addWidget(icon_bar)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)

        title = QLabel("报名统计")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text_primary}; border: none;")
        text_lay.addWidget(title)

        detail = QLabel(f"当前有效报名共 {count} 条")
        detail.setStyleSheet(f"font-size: 12px; color: {p.text_secondary}; border: none;")
        text_lay.addWidget(detail)

        lay.addLayout(text_lay, 1)
        frame.setLayout(lay)
        return frame

    def _build_upcoming_schedules_section(self, schedules: list[dict], p) -> QFrame:
        frame = QFrame()
        frame.setObjectName("upcomingFrame")
        frame.setStyleSheet(f"""
            QFrame#upcomingFrame {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout()
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QLabel("即将到来的排班")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text_primary}; border: none;")
        lay.addWidget(title)

        if not schedules:
            empty = QLabel("暂无即将到来的排班")
            empty.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; border: none;")
            lay.addWidget(empty)
        else:
            for sched in schedules:
                slot = sched.get("_slot", {})
                row_frame = QFrame()
                row_frame.setStyleSheet(f"""
                    QFrame {{
                        background: {p.bg_input};
                        border-left: 3px solid {p.success_fg};
                        border-radius: 6px;
                        padding: 2px 0;
                    }}
                """)
                row_lay = QHBoxLayout()
                row_lay.setContentsMargins(10, 6, 8, 6)
                row_lay.setSpacing(8)

                slot_name = QLabel(slot.get("name", "—"))
                slot_name.setStyleSheet(f"color: {p.text_primary}; font-weight: 500; border: none;")
                row_lay.addWidget(slot_name)

                row_lay.addStretch(1)

                start = slot.get("start_time", "")
                end = slot.get("end_time", "")
                time_text = ""
                if start:
                    try:
                        dt = datetime.fromisoformat(start)
                        time_text = dt.strftime("%m-%d %H:%M")
                        if end:
                            try:
                                dt_end = datetime.fromisoformat(end)
                                time_text += f"~{dt_end.strftime('%H:%M')}"
                            except (ValueError, TypeError):
                                pass
                    except (ValueError, TypeError):
                        pass
                if time_text:
                    time_label = QLabel(time_text)
                    time_label.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
                    row_lay.addWidget(time_label)

                row_frame.setLayout(row_lay)
                lay.addWidget(row_frame)

        frame.setLayout(lay)
        return frame


class _StatCard(QFrame):
    def __init__(self, label: str, value: int, accent_color: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(120)

        p = get_palette()
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-left: 4px solid {accent_color};
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        layout.addWidget(name_label)

        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        layout.addWidget(value_label)

        layout.addStretch(1)
        self.setLayout(layout)
