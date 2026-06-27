from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import ActivityStatus, User
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
)
from app.ui.style import get_palette
from app.ui.ui_utils import format_activity_status, to_utc


class DashboardPanel(QWidget):
    """概览面板：分为「当前信息」与「历史统计」两个选项卡。

    当前信息 tab 聚焦当下研判（报名中/待排班/待签到等），历史统计 tab 收纳全量计数。
    """

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

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QLabel("概览")
        header.setObjectName("pageTitle")
        root.addWidget(header)

        self._tabs = QTabWidget()
        p = get_palette()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{
                background: {p.btn_secondary_bg}; color: {p.btn_secondary_fg};
                border: none; border-radius: 8px; padding: 8px 20px;
                margin: 2px; font-weight: 600; font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {p.accent}; color: {p.text_on_accent};
            }}
            QTabBar::tab:hover:!selected {{
                background: {p.btn_secondary_hover};
            }}
        """)

        # —— Tab 1：当前信息 ——
        self._current_page = self._build_current_page()
        self._tabs.addTab(self._current_page, "当前信息")

        # —— Tab 2：历史统计 ——
        self._history_page = self._build_history_page()
        self._tabs.addTab(self._history_page, "历史统计")

        root.addWidget(self._tabs, 1)
        self.setLayout(root)

        self.refresh()

    # ── 页面构建 ──────────────────────────────────────────────

    def _build_current_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(16)

        desc = QLabel("当前活动与待办研判")
        desc.setObjectName("pageSubtitle")
        layout.addWidget(desc)

        self._current_grid = QGridLayout()
        self._current_grid.setHorizontalSpacing(16)
        self._current_grid.setVerticalSpacing(16)
        layout.addLayout(self._current_grid)

        self._current_section = QVBoxLayout()
        self._current_section.setSpacing(24)
        layout.addLayout(self._current_section)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setLayout(layout)
        scroll.setWidget(inner)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        page.setLayout(outer)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(16)

        desc = QLabel("历史全量统计")
        desc.setObjectName("pageSubtitle")
        layout.addWidget(desc)

        self._history_grid = QGridLayout()
        self._history_grid.setHorizontalSpacing(16)
        self._history_grid.setVerticalSpacing(16)
        layout.addLayout(self._history_grid)

        self._history_section = QVBoxLayout()
        self._history_section.setSpacing(24)
        layout.addLayout(self._history_section)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setLayout(layout)
        scroll.setWidget(inner)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        page.setLayout(outer)
        return page

    # ── data helpers ──────────────────────────────────────────

    def _is_admin(self) -> bool:
        return self._user.role.value in {"super_admin", "organizer"}

    def _current_stat_cards_data(self) -> list[tuple[str, int, str]]:
        """当前信息 tab 的卡片数据，聚焦当下研判。"""
        p = get_palette()
        if self._is_admin():
            # 管理端：活动生命周期分布
            return [
                ("报名中活动", self._count_open_active_activities(), "success_fg"),
                ("待排班活动", self._count_by_status(ActivityStatus.CLOSED), "warning_fg"),
                ("已归档活动", self._count_by_status(ActivityStatus.ARCHIVED), "text_tertiary"),
                ("当前可报名时段", self._count_upcoming_open_slots(), "accent"),
            ]
        # 学生端：待办提醒
        return [
            ("可报名活动", self._count_open_active_activities(), "accent"),
            ("我的待办报名", self._count_my_active_registrations(), "success_fg"),
            ("待签到排班", self._count_upcoming_schedules(), "warning_fg"),
            ("待签到时段", self._count_upcoming_open_slots(), "error_fg"),
        ]

    def _history_stat_cards_data(self) -> list[tuple[str, int, str]]:
        """历史统计 tab 的卡片数据，全量计数。"""
        p = get_palette()
        if self._is_admin():
            return [
                ("活动总数", self._activity_repo.count_all(), "accent"),
                ("时段总数", self._slot_repo.count_all(), "success_fg"),
                ("报名总数", self._reg_repo.count_all(), "warning_fg"),
                ("排班结果", self._schedule_repo.count_all(), "error_fg"),
            ]
        return [
            ("我的历史报名", self._reg_repo.count_by_user(self._user.id), "accent"),
            ("已结束排班", self._count_history_schedules(), "text_tertiary"),
        ]

    # ── 统计计算 ──────────────────────────────────────────────

    def _count_by_status(self, status: ActivityStatus) -> int:
        """按活动状态计数（带异常兜底）。"""
        try:
            return self._activity_repo.count_by_status(status)
        except Exception:
            return 0

    def _count_open_active_activities(self) -> int:
        """统计当前可报名（status=open 且 signup_end 未过期）的活动数。"""
        try:
            rows = self._activity_repo.list_by_status(ActivityStatus.OPEN)
        except Exception:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for row in rows:
            signup_end = row.get("signup_end", "")
            if not signup_end:
                continue
            try:
                if to_utc(signup_end) >= now:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def _count_upcoming_schedules(self) -> int:
        """统计尚未结束的排班数（slot.end_time > now）。"""
        try:
            rows = self._schedule_repo.list_by_user(self._user.id)
        except Exception:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for row in rows:
            slot = self._slot_repo.get(row.get("slot_id", ""))
            if not slot:
                continue
            end = slot.get("end_time", "")
            if not end:
                continue
            try:
                if to_utc(end) >= now:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def _count_history_schedules(self) -> int:
        """统计已结束的排班数（slot.end_time < now），用于历史统计。"""
        try:
            rows = self._schedule_repo.list_by_user(self._user.id)
        except Exception:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for row in rows:
            slot = self._slot_repo.get(row.get("slot_id", ""))
            if not slot:
                continue
            end = slot.get("end_time", "")
            if not end:
                continue
            try:
                if to_utc(end) < now:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def _count_upcoming_open_slots(self) -> int:
        """统计报名中活动里尚未结束的时段数。"""
        try:
            activities = self._activity_repo.list_by_status(ActivityStatus.OPEN)
        except Exception:
            return 0
        now = datetime.now(timezone.utc)
        active_ids: list[str] = []
        for act in activities:
            signup_end = act.get("signup_end", "")
            if not signup_end:
                continue
            try:
                if to_utc(signup_end) >= now:
                    active_ids.append(act.get("id", ""))
            except (ValueError, TypeError):
                continue
        count = 0
        for aid in active_ids:
            try:
                slots = self._slot_repo.list_by_activity(aid)
            except Exception:
                continue
            for slot in slots:
                end = slot.get("end_time", "")
                if not end:
                    continue
                try:
                    if to_utc(end) >= now:
                        count += 1
                except (ValueError, TypeError):
                    continue
        return count

    def _count_my_active_registrations(self) -> int:
        """统计当前/未来活动下的非取消报名数（作为待办提醒）。

        已归档活动的报名不计入待办。
        """
        try:
            regs = self._reg_repo.list_by_user(self._user.id)
        except Exception:
            return 0
        count = 0
        for reg in regs:
            if reg.get("status") == "cancelled":
                continue
            activity = self._activity_repo.get(reg.get("activity_id", ""))
            if not activity:
                continue
            # 已归档活动视为历史，不计入待办
            if activity.get("status") == ActivityStatus.ARCHIVED.value:
                continue
            count += 1
        return count

    def _recent_activities(self) -> list[dict]:
        """最近活动：admin 看全部，student 仅看报名中。"""
        if self._is_admin():
            rows = self._activity_repo.list_all()
        else:
            rows = self._activity_repo.list_by_status(ActivityStatus.OPEN)
        return rows[:5]

    def _upcoming_schedules(self) -> list[dict]:
        """学生端：未来 3 条排班作为待办提醒。"""
        rows = self._schedule_repo.list_by_user(self._user.id)
        now = datetime.now(timezone.utc)
        upcoming = []
        for row in rows:
            slot = self._slot_repo.get(row.get("slot_id", ""))
            if slot:
                end = slot.get("end_time", "")
                if end:
                    try:
                        if to_utc(end) >= now:
                            upcoming.append({**row, "_slot": slot})
                    except (ValueError, TypeError):
                        pass
        upcoming.sort(key=lambda r: r["_slot"].get("start_time", ""))
        return upcoming[:3]

    # ── build / refresh ───────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_current_tab()
        self._refresh_history_tab()

    def _clear_layout(self, layout) -> None:
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

    def _refresh_current_tab(self) -> None:
        self._clear_layout(self._current_grid)
        p = get_palette()
        for index, (label, value, color_key) in enumerate(self._current_stat_cards_data()):
            color = getattr(p, color_key, p.accent)
            card = _StatCard(label, value, color)
            row, col = divmod(index, 2)
            self._current_grid.addWidget(card, row, col)

        self._clear_layout(self._current_section)
        # 最近活动
        recent = self._recent_activities()
        if recent:
            self._current_section.addWidget(self._build_recent_activities_section(recent, p))
        # 学生端：即将到来的排班（待办提醒）
        if not self._is_admin():
            upcoming = self._upcoming_schedules()
            self._current_section.addWidget(self._build_upcoming_schedules_section(upcoming, p))

    def _refresh_history_tab(self) -> None:
        self._clear_layout(self._history_grid)
        p = get_palette()
        for index, (label, value, color_key) in enumerate(self._history_stat_cards_data()):
            color = getattr(p, color_key, p.accent)
            card = _StatCard(label, value, color)
            row, col = divmod(index, 2)
            self._history_grid.addWidget(card, row, col)

        self._clear_layout(self._history_section)
        # 管理端：历史报名总数概览
        if self._is_admin():
            count = self._reg_repo.count_all()
            self._history_section.addWidget(self._build_registrations_summary(count, p))

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
            "签到已结束": p.text_tertiary,
            "报名未开始": p.accent,
            "报名已截止": p.text_tertiary,
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

        title = QLabel("历史报名总数")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text_primary}; border: none;")
        text_lay.addWidget(title)

        detail = QLabel(f"累计报名记录共 {count} 条（含历史活动）")
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
