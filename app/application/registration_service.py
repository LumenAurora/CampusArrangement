from __future__ import annotations

from app.domain.exceptions import CapacityExceeded, ValidationError
from app.domain.models import Registration, SignupMode
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
        # 验证时段属于该活动
        slot = self._slot_repo.get(slot_id)
        if not slot or slot["activity_id"] != activity_id:
            raise ValidationError("所选时段不属于该活动")
        # 防止重复报名
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
        except Exception:
            if locked:
                self._slot_repo.release_slot(slot_id)
            raise
        return registration
