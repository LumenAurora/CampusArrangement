from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, Activity, ActivityStatus, ActivityType, CheckInMode, Role, SignupMode, SlotType, TimeSlot, User
from app.infrastructure.repositories import ActivityRepository, TimeSlotRepository


class ActivityService:
    def __init__(self, activity_repo: ActivityRepository, slot_repo: TimeSlotRepository) -> None:
        self._activity_repo = activity_repo
        self._slot_repo = slot_repo

    def create_activity(
        self,
        user: User,
        name: str,
        signup_start: datetime,
        signup_end: datetime,
        details: str,
        signup_mode: SignupMode = SignupMode.REALTIME,
        allocation_mode: AllocationMode = AllocationMode.GREEDY,
        location: str = "",
        activity_type: ActivityType = ActivityType.TIME_SLOT,
        checkin_mode: str = "manual",
        checkin_start: datetime | None = None,
        checkin_end: datetime | None = None,
        group_id: str | None = None,
    ) -> Activity:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可创建活动")
        if not name.strip():
            raise ValidationError("活动名称不能为空")
        if signup_end <= signup_start:
            raise ValidationError("报名截止时间必须晚于开始时间")
        # 校验签到模式
        try:
            checkin_mode_enum = CheckInMode(checkin_mode)
        except ValueError:
            raise ValidationError(f"无效的签到模式: {checkin_mode}")
        # 位置签到模式必须提供坐标格式的地点
        if checkin_mode_enum == CheckInMode.LOCATION:
            location_stripped = location.strip()
            if not location_stripped:
                raise ValidationError("位置签到模式必须填写活动地点坐标")
            if "," not in location_stripped:
                raise ValidationError("位置签到模式的地点必须为坐标格式，如：30.1234,120.5678")
            try:
                parts = location_stripped.split(",")
                float(parts[0].strip())
                float(parts[1].strip())
            except (ValueError, IndexError):
                raise ValidationError("位置签到模式的地点坐标格式无效，应为：纬度,经度")
        activity = Activity.create(
            name=name,
            owner_id=user.id,
            signup_start=signup_start,
            signup_end=signup_end,
            details=details,
            signup_mode=signup_mode,
            allocation_mode=allocation_mode,
            location=location,
            activity_type=activity_type,
            checkin_mode=checkin_mode_enum,
            checkin_start=checkin_start,
            checkin_end=checkin_end,
            group_id=group_id,
        )
        self._activity_repo.create(activity)
        return activity

    def add_position(
        self,
        user: User,
        activity_id: str,
        parent_slot_id: str,
        name: str,
        capacity: int,
    ) -> TimeSlot:
        """为时段添加子岗位（如：接待员、引导员等）"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("无权为该活动添加岗位")
        if user.role != Role.SUPER_ADMIN and activity["owner_id"] != user.id:
            raise PermissionDenied("无权为该活动添加岗位")
        if activity["status"] not in (ActivityStatus.DRAFT.value, ActivityStatus.PENDING_REVIEW.value):
            raise ValidationError("只有草稿或待审核状态的活动可以添加岗位")
        # 验证父时段存在且属于该活动
        parent = self._slot_repo.get(parent_slot_id)
        if not parent:
            raise ValidationError("父时段不存在")
        if parent["activity_id"] != activity_id:
            raise ValidationError("父时段不属于该活动")
        if parent.get("parent_slot_id"):
            raise ValidationError("不支持多层嵌套岗位")
        if not name.strip():
            raise ValidationError("岗位名称不能为空")
        if capacity < 1:
            raise ValidationError("岗位容量必须大于0")
        slot = TimeSlot.create_position(activity_id, parent_slot_id, name.strip(), capacity)
        self._slot_repo.create(slot)
        return slot

    def list_positions(self, parent_slot_id: str) -> list[dict]:
        """获取某时段下的所有子岗位"""
        return self._slot_repo.list_positions(parent_slot_id)

    def add_slot_generic(
        self,
        user: User,
        activity_id: str,
        slot_type: SlotType,
        name: str,
        capacity: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        metadata: str = "",
    ) -> TimeSlot:
        """添加通用报名选项（可以是时段、选题、课程等）"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("无权为该活动添加选项")
        if user.role != Role.SUPER_ADMIN and activity["owner_id"] != user.id:
            raise PermissionDenied("无权为该活动添加选项")
        if activity["status"] not in (ActivityStatus.DRAFT.value, ActivityStatus.PENDING_REVIEW.value):
            raise ValidationError("只有草稿或待审核状态的活动可以添加选项")
        if capacity < 1:
            raise ValidationError("选项容量必须大于0")
        if slot_type != SlotType.TIME_SLOT and not name.strip():
            raise ValidationError("非时段类型的选项名称不能为空")
        if slot_type == SlotType.TIME_SLOT:
            if not start_time or not end_time:
                raise ValidationError("时段类型必须设置开始和结束时间")
            if end_time <= start_time:
                raise ValidationError("时段结束时间必须晚于开始时间")
            slot = TimeSlot.create_time_slot(activity_id, start_time, end_time, capacity, name)
        elif slot_type == SlotType.TOPIC:
            slot = TimeSlot.create_topic(activity_id, name, capacity, metadata)
        elif slot_type == SlotType.COURSE:
            slot = TimeSlot.create_course(activity_id, name, capacity, metadata)
        else:
            raise ValidationError(f"不支持的选项类型: {slot_type}")
        self._slot_repo.create(slot)
        return slot

    def add_slot(
        self,
        user: User,
        activity_id: str,
        start_time: datetime,
        end_time: datetime,
        capacity: int,
        name: str = "",
    ) -> TimeSlot:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("无权为该活动添加时段")
        if user.role != Role.SUPER_ADMIN and activity["owner_id"] != user.id:
            raise PermissionDenied("无权为该活动添加时段")
        if activity["status"] not in (ActivityStatus.DRAFT.value, ActivityStatus.PENDING_REVIEW.value):
            raise ValidationError("只有草稿或待审核状态的活动可以添加时段")
        if end_time <= start_time:
            raise ValidationError("时段结束时间必须晚于开始时间")
        if capacity < 1:
            raise ValidationError("时段容量必须大于0")
        slot = TimeSlot.create_time_slot(activity_id=activity_id, start_time=start_time, end_time=end_time, capacity=capacity, name=name)
        self._slot_repo.create(slot)
        return slot

    def list_activities(self) -> list[dict]:
        return self._activity_repo.list_all()

    def list_open_activities(self) -> list[dict]:
        return self._activity_repo.list_by_status(ActivityStatus.OPEN)

    def list_slots(self, activity_id: str) -> list[dict]:
        return self._slot_repo.list_by_activity(activity_id)

    def get_activity(self, activity_id: str) -> dict | None:
        return self._activity_repo.get(activity_id)

    def delete_activity(self, user: User, activity_id: str) -> bool:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可删除活动")
        if user.role != Role.SUPER_ADMIN and activity["owner_id"] != user.id:
            raise PermissionDenied("无权删除该活动")
        if activity["status"] == ActivityStatus.OPEN.value:
            raise ValidationError("报名中的活动无法删除，请先结束报名")
        if activity["status"] == ActivityStatus.CLOSED.value:
            raise ValidationError("已结束的活动无法删除，请先归档")
        return self._activity_repo.delete(activity_id)

    def _check_owner_or_admin(self, user: User, activity: dict) -> None:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可操作")
        if user.role != Role.SUPER_ADMIN and activity["owner_id"] != user.id:
            raise PermissionDenied("无权操作该活动")

    def _check_reviewer(self, user: User, activity: dict) -> None:
        """审核人不能是活动创建者"""
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可审核")
        if activity["owner_id"] == user.id:
            raise PermissionDenied("不能审核自己创建的活动")

    def publish_activity(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        # 超级管理员可直接从DRAFT/PENDING_REVIEW发布
        if user.role == Role.SUPER_ADMIN:
            if activity["status"] not in (ActivityStatus.DRAFT.value, ActivityStatus.PENDING_REVIEW.value):
                raise ValidationError("只有草稿或待审核状态的活动可以发布")
        else:
            # 组织者只能从PENDING_REVIEW状态发布（必须先提交审核）
            if activity["status"] != ActivityStatus.PENDING_REVIEW.value:
                raise ValidationError("组织者需先提交审核，审核通过后方可发布")
            # 审核人不能是活动创建者
            self._check_reviewer(user, activity)
        slots = self._slot_repo.list_by_activity(activity_id)
        if not slots:
            raise ValidationError("请先添加至少一个选项再发布")
        self._activity_repo.update_status(activity_id, ActivityStatus.OPEN)

    def close_activity(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        if activity["status"] != ActivityStatus.OPEN.value:
            raise ValidationError("只有报名中的活动可以结束报名")
        self._activity_repo.update_status(activity_id, ActivityStatus.CLOSED)

    def reopen_activity(self, user: User, activity_id: str) -> None:
        """重新开放已关闭的活动（用于排班失败回滚等场景）"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        if activity["status"] != ActivityStatus.CLOSED.value:
            raise ValidationError("只有已关闭的活动可以重新开放")
        self._activity_repo.update_status(activity_id, ActivityStatus.OPEN)

    def archive_activity(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        if activity["status"] != ActivityStatus.CLOSED.value:
            raise ValidationError("只有已结束的活动可以归档")
        self._activity_repo.update_status(activity_id, ActivityStatus.ARCHIVED)

    def submit_for_review(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        if activity["status"] != ActivityStatus.DRAFT.value:
            raise ValidationError("只有草稿状态的活动可以提交审核")
        slots = self._slot_repo.list_by_activity(activity_id)
        if not slots:
            raise ValidationError("请先添加至少一个选项再提交审核")
        self._activity_repo.update_status(activity_id, ActivityStatus.PENDING_REVIEW)

    def duplicate_activity(
        self,
        user: User,
        activity_id: str,
        new_signup_start: datetime,
        new_signup_end: datetime,
        new_checkin_start: datetime | None = None,
        new_checkin_end: datetime | None = None,
    ) -> Activity:
        """复制活动并调整报名时间，用于创建周期性活动"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可复制活动")
        
        if new_signup_end <= new_signup_start:
            raise ValidationError("新报名截止时间必须晚于开始时间")
        
        new_activity = Activity.create(
            name=activity["name"],
            owner_id=user.id,
            signup_start=new_signup_start,
            signup_end=new_signup_end,
            details=activity["details"],
            signup_mode=SignupMode(activity["signup_mode"]),
            allocation_mode=AllocationMode(activity["allocation_mode"]),
            location=activity["location"],
            activity_type=ActivityType(activity.get("activity_type", "time_slot")),
            checkin_mode=CheckInMode(activity["checkin_mode"]),
            checkin_start=new_checkin_start,
            checkin_end=new_checkin_end,
            group_id=activity.get("group_id"),
        )
        self._activity_repo.create(new_activity)

        slots = self._slot_repo.list_by_activity(activity_id)
        # 计算时间偏移：统一去除时区信息后再相减，只关心挂钟时间的差值
        old_start = datetime.fromisoformat(activity["signup_start"])
        if old_start.tzinfo is not None:
            old_start = old_start.replace(tzinfo=None)
        new_start = new_signup_start.replace(tzinfo=None) if new_signup_start.tzinfo is not None else new_signup_start
        signup_diff = new_start - old_start

        # 先复制父级 slot，建立 ID 映射
        old_to_new_slot_id: dict[str, str] = {}
        for slot in slots:
            if slot.get("parent_slot_id"):
                continue  # 子岗位在第二轮处理
            slot_type = SlotType(slot.get("slot_type", "time_slot"))
            name = slot.get("name", "")
            metadata = slot.get("metadata", "")
            capacity = slot["capacity"]

            if slot_type == SlotType.TIME_SLOT and slot.get("start_time") and slot.get("end_time"):
                slot_start = datetime.fromisoformat(slot["start_time"])
                slot_end = datetime.fromisoformat(slot["end_time"])
                # 去除时区信息以进行挂钟时间偏移
                if slot_start.tzinfo is not None:
                    slot_start = slot_start.replace(tzinfo=None)
                if slot_end.tzinfo is not None:
                    slot_end = slot_end.replace(tzinfo=None)
                new_slot_start = slot_start + signup_diff
                new_slot_end = slot_end + signup_diff
                new_slot = TimeSlot.create_time_slot(
                    new_activity.id, new_slot_start, new_slot_end, capacity, name,
                )
            elif slot_type == SlotType.TOPIC:
                new_slot = TimeSlot.create_topic(new_activity.id, name, capacity, metadata)
            elif slot_type == SlotType.COURSE:
                new_slot = TimeSlot(
                    id=str(uuid4()),
                    activity_id=new_activity.id,
                    slot_type=SlotType.COURSE,
                    name=name,
                    capacity=capacity,
                    used_count=0,
                    parent_slot_id=None,
                    metadata=metadata,
                )
            else:
                new_slot = TimeSlot(
                    id=str(uuid4()),
                    activity_id=new_activity.id,
                    slot_type=slot_type,
                    name=name,
                    capacity=capacity,
                    used_count=0,
                    parent_slot_id=None,
                    metadata=metadata,
                )
            self._slot_repo.create(new_slot)
            old_to_new_slot_id[slot["id"]] = new_slot.id

        # 复制子岗位
        for slot in slots:
            if not slot.get("parent_slot_id"):
                continue
            new_parent_id = old_to_new_slot_id.get(slot["parent_slot_id"])
            if not new_parent_id:
                continue
            new_slot = TimeSlot.create_position(
                new_activity.id, new_parent_id, slot.get("name", ""), slot["capacity"],
            )
            self._slot_repo.create(new_slot)
        
        return new_activity

    def reject_activity(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        # 退回是审核操作，审核人不能是活动创建者
        self._check_reviewer(user, activity)
        if activity["status"] != ActivityStatus.PENDING_REVIEW.value:
            raise ValidationError("只有待审核的活动可以退回")
        self._activity_repo.update_status(activity_id, ActivityStatus.DRAFT)
