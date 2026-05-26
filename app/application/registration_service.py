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
        if activity.get("signup_mode") == SignupMode.REALTIME.value:
            locked = self._slot_repo.lock_slot(slot_id)
            if not locked:
                raise CapacityExceeded("名额已满")
        registration = Registration.create(user_id=user_id, activity_id=activity_id, slot_id=slot_id, priority=priority)
        self._reg_repo.create(registration)
        return registration
