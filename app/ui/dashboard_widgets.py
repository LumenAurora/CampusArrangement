from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QDate, Qt
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
from app.ui.calendar_widgets import ActivityCalendar
from app.ui.style import get_palette
from app.ui.ui_utils import format_activity_status, to_local, to_utc


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

        # 持久日历区块：admin 模式下显示，由 _refresh_current_tab 控制可见性与数据
        self._calendar_section = _CalendarSection(self._activity_repo, self._slot_repo, self._user)
        self._calendar_section.setVisible(False)
        layout.addWidget(self._calendar_section)

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
            ("可报名时段", self._count_upcoming_open_slots(), "error_fg"),
        ]

    def _history_stat_cards_data(self) -> list[tuple[str, int, str]]:
        """历史统计 tab 的卡片数据，全量计数。"""
        if self._is_admin():
            return [
                ("活动总数", self._safe_count(self._activity_repo.count_all), "accent"),
                ("时段总数", self._safe_count(self._slot_repo.count_all), "success_fg"),
                ("报名总数", self._safe_count(self._reg_repo.count_all), "warning_fg"),
                ("排班结果", self._safe_count(self._schedule_repo.count_all), "error_fg"),
            ]
        return [
            ("我的历史报名", self._safe_count(lambda: self._reg_repo.count_by_user(self._user.id)), "accent"),
            ("已结束排班", self._count_history_schedules(), "text_tertiary"),
        ]

    def _safe_count(self, fn) -> int:
        """安全调用仓库计数方法，异常时返回 0，避免单次计数失败拖垮整个面板。"""
        try:
            return int(fn())
        except Exception:
            return 0

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
            try:
                slot = self._slot_repo.get(row.get("slot_id", ""))
                if not slot:
                    continue
                end = slot.get("end_time", "")
                if not end:
                    continue
                if to_utc(end) >= now:
                    count += 1
            except Exception:
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
            try:
                slot = self._slot_repo.get(row.get("slot_id", ""))
                if not slot:
                    continue
                end = slot.get("end_time", "")
                if not end:
                    continue
                if to_utc(end) < now:
                    count += 1
            except Exception:
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
            try:
                if reg.get("status") == "cancelled":
                    continue
                activity = self._activity_repo.get(reg.get("activity_id", ""))
                if not activity:
                    continue
                # 已归档活动视为历史，不计入待办
                if activity.get("status") == ActivityStatus.ARCHIVED.value:
                    continue
                count += 1
            except Exception:
                continue
        return count

    def _recent_activities(self) -> list[dict]:
        """最近活动：admin 看全部，student 仅看报名中。"""
        try:
            if self._is_admin():
                rows = self._activity_repo.list_all()
            else:
                rows = self._activity_repo.list_by_status(ActivityStatus.OPEN)
        except Exception:
            return []
        return rows[:5]

    def _upcoming_schedules(self) -> list[dict]:
        """学生端：未来 3 条排班作为待办提醒。"""
        try:
            rows = self._schedule_repo.list_by_user(self._user.id)
        except Exception:
            return []
        now = datetime.now(timezone.utc)
        upcoming = []
        for row in rows:
            try:
                slot = self._slot_repo.get(row.get("slot_id", ""))
                if slot:
                    end = slot.get("end_time", "")
                    if end:
                        if to_utc(end) >= now:
                            upcoming.append({**row, "_slot": slot})
            except Exception:
                continue
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
        # 管理端：可视化日历区块（展示活动报名与时段分布）
        # 学生端：即将到来的排班（待办提醒）
        if self._is_admin():
            self._calendar_section.refresh()
            self._calendar_section.setVisible(True)
        else:
            self._calendar_section.setVisible(False)
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
        # 管理端：历史报名总数概览（与卡片一致采用 _safe_count 兜底，避免单次失败拖垮面板）
        if self._is_admin():
            count = self._safe_count(self._reg_repo.count_all)
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


class _CalendarSection(QFrame):
    """管理端概览日历：可视化展示所有活动的报名开始与时段分布。

    数据来源：activity_repo.list_all() + slot_repo.list_by_activity(aid)。
    事件类型沿用 ActivityCalendar 的配色约定：
        - "activity"（报名开始）→ accent
        - "schedule"（活动时段）  → success_fg
    """

    def __init__(
        self,
        activity_repo: ActivityRepository,
        slot_repo: TimeSlotRepository,
        user: User,
    ) -> None:
        super().__init__()
        self._activity_repo = activity_repo
        self._slot_repo = slot_repo
        self._user = user
        self._events_by_date: dict[QDate, list[dict]] = {}

        p = get_palette()
        self.setObjectName("calendarSectionFrame")
        self.setStyleSheet(f"""
            QFrame#calendarSectionFrame {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-radius: 16px;
            }}
        """)

        lay = QVBoxLayout()
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # 头部：标题 + 图例
        header_lay = QHBoxLayout()
        title = QLabel("活动日历")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text_primary}; border: none;")
        header_lay.addWidget(title)
        header_lay.addStretch(1)
        legend_lay = QHBoxLayout()
        legend_lay.setSpacing(12)
        for label, color_key in (("报名开始", "accent"), ("活动时段", "success_fg")):
            dot = QFrame()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {getattr(p, color_key)}; border-radius: 4px;")
            legend_lay.addWidget(dot)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {p.text_secondary}; font-size: 11px; border: none;")
            legend_lay.addWidget(lbl)
        header_lay.addLayout(legend_lay)
        lay.addLayout(header_lay)

        # 日历主体：复用已有 ActivityCalendar（自带 paintCell 着色）
        self._calendar = ActivityCalendar()
        lay.addWidget(self._calendar)

        # 选中日期的详情区
        self._info_label = QLabel("点击日期查看当日活动详情")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"color: {p.text_tertiary}; font-size: 12px; border: none; padding: 4px 0;"
        )
        lay.addWidget(self._info_label)

        self._calendar.date_selected.connect(self._on_date_selected)

        self.setLayout(lay)

    def refresh(self) -> None:
        try:
            events_by_date = self._collect_events()
        except Exception:
            # 收集失败时清空事件，避免日历渲染异常
            events_by_date = {}
        self._events_by_date = events_by_date
        try:
            self._calendar.set_events(events_by_date)
        except Exception:
            pass
        # 刷新后展示当日摘要
        try:
            self._on_date_selected(self._calendar.selectedDate())
        except Exception:
            self._info_label.setText("点击日期查看当日活动详情")

    def _collect_events(self) -> dict[QDate, list[dict]]:
        """收集活动报名开始事件 + 时段事件，按日期聚合。

        所有仓库调用都做异常兜底，单条数据异常不影响整体日历。
        所有时间统一用 to_local 转回本地时区，确保 QDate 与小时:分钟展示为
        用户所在时区的「墙上时间」，而非 UTC（否则跨时区会落在错误日期）。
        """
        events_by_date: dict[QDate, list[dict]] = {}
        try:
            activities = self._activity_repo.list_all()
        except Exception:
            return events_by_date

        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "未知活动")
            activity_location = activity.get("location", "")

            # 1) 报名开始事件
            signup_start = activity.get("signup_start", "")
            if signup_start:
                try:
                    dt = to_local(signup_start)
                    qdate = QDate(dt.year, dt.month, dt.day)
                    events_by_date.setdefault(qdate, []).append({
                        "id": f"activity:{activity_id}",
                        "title": activity_name,
                        "type": "activity",
                        "time_range": dt.strftime("%H:%M") + " 开始报名",
                        "location": activity_location,
                    })
                except Exception:
                    pass

            # 2) 时段事件
            try:
                slots = self._slot_repo.list_by_activity(activity_id)
            except Exception:
                slots = []
            for slot in slots:
                try:
                    start_str = slot.get("start_time", "")
                    if not start_str:
                        continue
                    dt = to_local(start_str)
                    qdate = QDate(dt.year, dt.month, dt.day)
                    end_str = slot.get("end_time", "")
                    end_dt = to_local(end_str) if end_str else None
                    time_range = dt.strftime("%H:%M")
                    if end_dt:
                        time_range += f" - {end_dt.strftime('%H:%M')}"
                    events_by_date.setdefault(qdate, []).append({
                        "id": f"slot:{slot.get('id', '')}",
                        "title": activity_name,
                        "type": "schedule",
                        "time_range": time_range,
                        "location": activity_location,
                    })
                except Exception:
                    continue

        return events_by_date

    def _on_date_selected(self, date: QDate) -> None:
        events = self._events_by_date.get(date, [])
        if not events:
            self._info_label.setText(f"{date.toString('yyyy-MM-dd')} 当日无活动安排")
            return
        # 按时间排序，最多展示 5 条
        sorted_events = sorted(events, key=lambda e: e.get("time_range", ""))
        lines = [f"{date.toString('yyyy-MM-dd')} 共 {len(events)} 项安排："]
        for ev in sorted_events[:5]:
            prefix = "报名" if ev.get("type") == "activity" else "时段"
            lines.append(f"  • [{prefix}] {ev.get('title', '—')}  {ev.get('time_range', '')}")
        if len(events) > 5:
            lines.append(f"  …其余 {len(events) - 5} 项")
        self._info_label.setText("\n".join(lines))
