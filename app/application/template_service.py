"""活动模板服务 — 模板 CRUD 与周期活动批量生成。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.activity_service import ActivityService
from app.domain.exceptions import ValidationError
from app.domain.models import ActivityType, AllocationMode, CheckInMode, SignupMode, User
from app.domain.templates import (
    ActivityTemplate,
    RecurrencePattern,
    load_templates,
    save_templates,
)


class TemplateService:
    """活动模板管理服务。"""

    def list_templates(self) -> list[ActivityTemplate]:
        """获取所有模板。"""
        return load_templates()

    def get_template(self, template_id: str) -> ActivityTemplate | None:
        """获取单个模板。"""
        templates = load_templates()
        for t in templates:
            if t.id == template_id:
                return t
        return None

    def save_template(
        self,
        name: str,
        description: str,
        activity_type: str,
        signup_mode: str,
        allocation_mode: str,
        checkin_mode: str,
        allow_multiple_slots: bool,
        slot_templates: list[dict],
        recurrence: str = "once",
    ) -> ActivityTemplate:
        """保存新模板。"""
        templates = load_templates()
        now = datetime.now().isoformat()
        tpl = ActivityTemplate(
            id=str(uuid4()),
            name=name,
            description=description,
            activity_type=activity_type,
            signup_mode=signup_mode,
            allocation_mode=allocation_mode,
            checkin_mode=checkin_mode,
            allow_multiple_slots=allow_multiple_slots,
            slot_templates=slot_templates,
            recurrence=recurrence,
            created_at=now,
            updated_at=now,
        )
        templates.append(tpl)
        save_templates(templates)
        return tpl

    def delete_template(self, template_id: str) -> bool:
        """删除模板。内置模板不可删除。"""
        templates = load_templates()
        # 内置模板以 tpl_ 开头且是预定义的
        builtin_ids = {"tpl_weekly_volunteer", "tpl_monthly_duty", "tpl_semester_course", "tpl_one_time_event"}
        if template_id in builtin_ids:
            raise ValidationError("内置模板不可删除")
        for i, t in enumerate(templates):
            if t.id == template_id:
                templates.pop(i)
                save_templates(templates)
                return True
        return False


def generate_recurring_activities(
    activity_service: ActivityService,
    template_service: TemplateService,
    user: User,
    template_id: str,
    base_name: str,
    first_signup_start: datetime,
    signup_duration_hours: int = 72,
    count: int = 1,
    recurrence: str = "once",
) -> list[dict]:
    """基于模板批量生成周期活动。

    参数:
        activity_service: 活动服务（提供 create_activity / add_slot）
        template_service: 模板服务
        user: 当前用户
        template_id: 模板 ID
        base_name: 活动基础名称（会自动加序号）
        first_signup_start: 第一个活动的报名开始时间
        signup_duration_hours: 每次报名窗口持续时间（默认 72h）
        count: 生成的活动数量（默认 1）
        recurrence: 周期模式（once / weekly / monthly / semester）

    返回:
        创建的活动 dict 列表
    """
    template = template_service.get_template(template_id)
    if not template:
        raise ValidationError("模板不存在")

    created_activities: list[dict] = []

    # 计算报名窗口间隔
    if recurrence == RecurrencePattern.WEEKLY:
        interval = timedelta(days=7)
    elif recurrence == RecurrencePattern.MONTHLY:
        interval = timedelta(days=28)  # 近似一个月
    elif recurrence == RecurrencePattern.SEMESTER:
        # 整学期：只创建一个活动，报名窗口覆盖整个学期（约 5 个月）
        count = 1
        interval = timedelta(days=1)  # 不用于循环
    else:
        interval = timedelta(days=1)  # 不用于循环

    signup_start = first_signup_start
    for i in range(count):
        # 生成活动名称
        if count > 1:
            name = f"{base_name} (第{i + 1}周)" if recurrence == RecurrencePattern.WEEKLY else f"{base_name} (第{i + 1}期)"
        else:
            name = base_name

        signup_end = signup_start + timedelta(hours=signup_duration_hours)

        # 整学期模式：报名窗口拉长到 5 个月
        if recurrence == RecurrencePattern.SEMESTER:
            signup_end = signup_start + timedelta(days=150)

        try:
            # 创建活动
            activity = activity_service.create_activity(
                user=user,
                name=name,
                signup_start=signup_start,
                signup_end=signup_end,
                details=template.description,
                signup_mode=SignupMode(template.signup_mode),
                allocation_mode=AllocationMode(template.allocation_mode),
                location="",
                activity_type=ActivityType(template.activity_type),
                checkin_mode=template.checkin_mode,
                checkin_start=signup_start,
                checkin_end=signup_end,
                group_id=None,
                allow_multiple_slots=template.allow_multiple_slots,
            )

            # 从模板生成时段
            for st in template.slot_templates:
                try:
                    name_str = st.get("name", "")
                    capacity = st.get("capacity", 30)
                    if "hour_start" in st and "hour_end" in st:
                        # 有时段的模板：基于当前日期创建
                        slot_day = signup_end.date() if recurrence != RecurrencePattern.SEMESTER else signup_start.date()
                        start_time = datetime.combine(
                            slot_day,
                            datetime.min.time().replace(hour=st["hour_start"]),
                        ).replace(tzinfo=timezone.utc)
                        end_time = datetime.combine(
                            slot_day,
                            datetime.min.time().replace(hour=st["hour_end"]),
                        ).replace(tzinfo=timezone.utc)
                        activity_service.add_slot(
                            user=user,
                            activity_id=activity.id,
                            name=name_str,
                            start_time=start_time,
                            end_time=end_time,
                            capacity=capacity,
                        )
                    elif template.activity_type == "non_time_slot":
                        # 非时段模式：添加选题/课程等选项
                        from app.domain.models import SlotType
                        activity_service.add_slot_generic(
                            user=user,
                            activity_id=activity.id,
                            slot_type=SlotType.TOPIC if "选题" in name_str else SlotType.CUSTOM_OPTION,
                            name=name_str,
                            capacity=capacity,
                        )
                except Exception:
                    # 单个时段失败不影响整体
                    pass

            created_activities.append({
                "id": activity.id,
                "name": name,
                "status": "draft",
            })
        except Exception as e:
            # 单个活动创建失败继续尝试后续
            pass

        # 推进到下一个报名周期
        signup_start = signup_start + interval

    return created_activities
