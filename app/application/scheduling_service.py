from __future__ import annotations

from app.domain.exceptions import ValidationError
from app.domain.models import ActivityStatus, AllocationMode, RegistrationStatus, SignupMode
from app.domain.services import schedule_registrations
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository, ScheduleRepository, TimeSlotRepository


class SchedulingService:
    def __init__(
        self,
        reg_repo: RegistrationRepository,
        slot_repo: TimeSlotRepository,
        schedule_repo: ScheduleRepository,
        activity_repo: ActivityRepository,
    ) -> None:
        self._reg_repo = reg_repo
        self._slot_repo = slot_repo
        self._schedule_repo = schedule_repo
        self._activity_repo = activity_repo

    def run(self, activity_id: str) -> int:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity["status"] not in (ActivityStatus.CLOSED.value, ActivityStatus.OPEN.value):
            raise ValidationError("只有已结束或报名中的活动可以执行排班")
        allocation_mode = AllocationMode(activity["allocation_mode"])
        registrations = self._reg_repo.list_pending(activity_id)
        slots = self._slot_repo.list_by_activity(activity_id)
        if not registrations:
            raise ValidationError("没有待处理的报名记录")
        if not slots:
            raise ValidationError("没有可用的时段")
        assignments = schedule_registrations(
            registrations=self._reg_repo.to_models(registrations),
            slots=self._slot_repo.to_models(slots),
            mode=allocation_mode,
        )
        self._slot_repo.reset_used_counts_for_activity(activity_id)
        self._schedule_repo.clear_for_activity(activity_id)
        slot_assign_count: dict[str, int] = {}
        assigned_user_ids: set[str] = set()
        for assignment in assignments:
            self._schedule_repo.create(assignment)
            assigned_user_ids.add(assignment.user_id)
            slot_assign_count[assignment.slot_id] = slot_assign_count.get(assignment.slot_id, 0) + 1
        for slot_id, count in slot_assign_count.items():
            self._slot_repo.increment_used_count(slot_id, count)
        is_realtime = activity.get("signup_mode") == SignupMode.REALTIME.value
        for reg in registrations:
            if reg["user_id"] in assigned_user_ids:
                self._reg_repo.update_status(reg["id"], RegistrationStatus.ASSIGNED)
            else:
                if is_realtime:
                    self._slot_repo.release_slot(reg["slot_id"])
                self._reg_repo.update_status(reg["id"], RegistrationStatus.CANCELLED)
        return len(assignments)
