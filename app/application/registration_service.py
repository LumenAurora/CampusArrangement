from __future__ import annotations

from app.domain.exceptions import CapacityExceeded, ConflictError, ValidationError
from app.domain.models import ActivityStatus, Registration, RegistrationStatus, SignupMode
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository, TimeSlotRepository


class RegistrationService:
    def __init__(
        self,
        slot_repo: TimeSlotRepository,
        reg_repo: RegistrationRepository,
        activity_repo: ActivityRepository,
    ) -> None:
        self._slot_repo = slot_repo
        self._reg_repo = reg_repo
        self._activity_repo = activity_repo

    def register(self, user_id: str, activity_id: str, slot_id: str, priority: int) -> Registration:
        if priority < 1:
            raise ValidationError("志愿优先级必须大于等于1")
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity["status"] != ActivityStatus.OPEN.value:
            raise ValidationError("该活动当前不在报名中")
        slot = self._slot_repo.get(slot_id)
        if not slot or slot["activity_id"] != activity_id:
            raise ValidationError("所选时段不属于该活动")
        existing = self._reg_repo.list_by_user_activity(user_id, activity_id)
        if existing:
            raise ValidationError("您已报名该活动，请勿重复报名")
        locked = False
        if activity.get("signup_mode") == SignupMode.REALTIME.value:
            locked = self._slot_repo.lock_slot(slot_id)
            if not locked:
                raise CapacityExceeded("名额已满")
        try:
            registration = Registration.create(
                user_id=user_id, activity_id=activity_id, slot_id=slot_id, priority=priority,
            )
            self._reg_repo.create(registration)
        except ConflictError:
            if locked:
                self._slot_repo.release_slot(slot_id)
            raise
        except Exception:
            if locked:
                self._slot_repo.release_slot(slot_id)
            raise
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
        if activity and activity["status"] == ActivityStatus.ARCHIVED.value:
            raise ValidationError("已归档的活动无法取消报名")
        if activity and activity.get("signup_mode") == SignupMode.REALTIME.value:
            self._slot_repo.release_slot(reg["slot_id"])
        self._reg_repo.update_status(registration_id, RegistrationStatus.CANCELLED)

    def list_user_registrations(self, user_id: str) -> list[dict]:
        return self._reg_repo.list_by_user(user_id)
