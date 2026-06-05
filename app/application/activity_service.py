from __future__ import annotations

from datetime import datetime

from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, Activity, ActivityStatus, CheckInMode, Role, SignupMode, TimeSlot, User
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
        checkin_mode: str = "manual",
        checkin_start: datetime | None = None,
        checkin_end: datetime | None = None,
    ) -> Activity:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可创建活动")
        if not name.strip():
            raise ValidationError("活动名称不能为空")
        if signup_end <= signup_start:
            raise ValidationError("报名截止时间必须晚于开始时间")
        try:
            checkin_mode_enum = CheckInMode(checkin_mode)
        except ValueError:
            raise ValidationError(f"无效的签到模式: {checkin_mode}")
        activity = Activity.create(
            name=name,
            owner_id=user.id,
            signup_start=signup_start,
            signup_end=signup_end,
            details=details,
            signup_mode=signup_mode,
            allocation_mode=allocation_mode,
            location=location,
            checkin_mode=checkin_mode_enum,
            checkin_start=checkin_start,
            checkin_end=checkin_end,
        )
        self._activity_repo.create(activity)
        return activity

    def add_slot(
        self,
        user: User,
        activity_id: str,
        start_time: datetime,
        end_time: datetime,
        capacity: int,
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
        slot = TimeSlot.create(activity_id=activity_id, start_time=start_time, end_time=end_time, capacity=capacity)
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
            raise ValidationError("请先添加至少一个时段再发布")
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
            raise ValidationError("请先添加至少一个时段再提交审核")
        self._activity_repo.update_status(activity_id, ActivityStatus.PENDING_REVIEW)

    def reject_activity(self, user: User, activity_id: str) -> None:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        # 退回是审核操作，审核人不能是活动创建者
        self._check_reviewer(user, activity)
        if activity["status"] != ActivityStatus.PENDING_REVIEW.value:
            raise ValidationError("只有待审核的活动可以退回")
        self._activity_repo.update_status(activity_id, ActivityStatus.DRAFT)
