from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.domain.exceptions import CapacityExceeded, ConflictError, ValidationError
from app.domain.models import ActivityStatus, Registration, RegistrationStatus, SignupMode
from app.infrastructure.db import transaction
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository, TimeSlotRepository

if TYPE_CHECKING:
    from app.infrastructure.repositories import GroupRepository


class RegistrationService:
    def __init__(
        self,
        slot_repo: TimeSlotRepository,
        reg_repo: RegistrationRepository,
        activity_repo: ActivityRepository,
        group_repo: GroupRepository | None = None,
    ) -> None:
        self._slot_repo = slot_repo
        self._reg_repo = reg_repo
        self._activity_repo = activity_repo
        self._group_repo = group_repo

    def register(self, user_id: str, activity_id: str, slot_id: str, priority: int) -> Registration:
        if priority < 1:
            raise ValidationError("志愿优先级必须大于等于1")
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity["status"] != ActivityStatus.OPEN.value:
            raise ValidationError("该活动当前不在报名中")
        # 校验小组权限：如果活动有小组限制，检查用户是否是成员
        if self._group_repo and activity.get("group_id"):
            if not self._group_repo.is_member(activity["group_id"], user_id):
                raise ValidationError("该活动仅限小组成员报名，请先加入对应小组")
        # 校验报名时间窗口
        now = datetime.now(timezone.utc)
        signup_start = activity.get("signup_start")
        signup_end = activity.get("signup_end")
        if signup_start:
            start = datetime.fromisoformat(str(signup_start)) if isinstance(signup_start, str) else signup_start
            start = start.astimezone(timezone.utc)
            if now < start:
                raise ValidationError("报名尚未开始")
        if signup_end:
            end = datetime.fromisoformat(str(signup_end)) if isinstance(signup_end, str) else signup_end
            end = end.astimezone(timezone.utc)
            if now > end:
                raise ValidationError("报名已截止")
        slot = self._slot_repo.get(slot_id)
        if not slot or slot["activity_id"] != activity_id:
            raise ValidationError("所选时段不属于该活动")

        # 如果用户有NOT_ASSIGNED记录，先将其置为CANCELLED以允许重新报名
        existing = self._reg_repo.list_by_user_activity(user_id, activity_id)
        not_assigned_ids = [r["id"] for r in existing if r["status"] == RegistrationStatus.NOT_ASSIGNED.value]
        active_existing = [r for r in existing if r["status"] not in (RegistrationStatus.CANCELLED.value, RegistrationStatus.NOT_ASSIGNED.value)]
        if active_existing:
            raise ValidationError("您已报名该活动，请勿重复报名")

        registration = Registration.create(
            user_id=user_id, activity_id=activity_id, slot_id=slot_id, priority=priority,
        )
        if activity.get("signup_mode") == SignupMode.REALTIME.value:
            with transaction() as conn:
                # 先取消NOT_ASSIGNED记录
                for rid in not_assigned_ids:
                    self._reg_repo.update_status(rid, RegistrationStatus.CANCELLED, conn=conn)
                locked = self._slot_repo.lock_slot(slot_id, conn=conn)
                if not locked:
                    raise CapacityExceeded("名额已满")
                try:
                    self._reg_repo.create(registration, conn=conn)
                except Exception:
                    self._slot_repo.release_slot(slot_id, conn=conn)
                    raise
        else:
            # BLIND模式也使用事务保证原子性
            with transaction() as conn:
                for rid in not_assigned_ids:
                    self._reg_repo.update_status(rid, RegistrationStatus.CANCELLED, conn=conn)
                self._reg_repo.create(registration, conn=conn)
        return registration

    def cancel(self, user_id: str, registration_id: str) -> None:
        reg = self._reg_repo.get(registration_id)
        if not reg:
            raise ValidationError("报名记录不存在")
        if reg["user_id"] != user_id:
            raise ValidationError("只能取消自己的报名")
        if reg["status"] == RegistrationStatus.CANCELLED.value:
            raise ValidationError("该报名已取消")
        if reg["status"] == RegistrationStatus.ASSIGNED.value:
            raise ValidationError("已分配的报名无法取消，请联系管理员")
        activity = self._activity_repo.get(reg["activity_id"])
        if activity and activity["status"] == ActivityStatus.CLOSED.value:
            raise ValidationError("报名已结束，如需取消请联系组织者请假")
        if activity and activity["status"] == ActivityStatus.ARCHIVED.value:
            raise ValidationError("已归档的活动无法取消报名")
        # Only release the slot if the registration is PENDING in realtime mode.
        # NOT_ASSIGNED registrations should NOT release the slot because
        # SchedulingService.run already recalculated used_count based on
        # actual assignments, and NOT_ASSIGNED users are not counted.
        if (activity and activity.get("signup_mode") == SignupMode.REALTIME.value
                and reg["status"] == RegistrationStatus.PENDING.value):
            with transaction() as conn:
                self._slot_repo.release_slot(reg["slot_id"], conn=conn)
                self._reg_repo.update_status(registration_id, RegistrationStatus.CANCELLED, conn=conn)
        else:
            self._reg_repo.update_status(registration_id, RegistrationStatus.CANCELLED)

    def list_user_registrations(self, user_id: str) -> list[dict]:
        return self._reg_repo.list_by_user(user_id)
