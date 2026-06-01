from __future__ import annotations

from app.domain.models import AllocationMode, RegistrationStatus
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
        allocation_mode = AllocationMode(activity["allocation_mode"]) if activity else AllocationMode.GREEDY
        registrations = self._reg_repo.list_pending(activity_id)
        slots = self._slot_repo.list_by_activity(activity_id)
        assignments = schedule_registrations(
            registrations=self._reg_repo.to_models(registrations),
            slots=self._slot_repo.to_models(slots),
            mode=allocation_mode,
        )
        self._schedule_repo.clear_for_activity(activity_id)
        assigned_user_ids: set[str] = set()
        for assignment in assignments:
            self._schedule_repo.create(assignment)
            assigned_user_ids.add(assignment.user_id)
        # 将已分配的报名记录标记为 ASSIGNED
        for reg in registrations:
            if reg["user_id"] in assigned_user_ids:
                self._reg_repo.update_status(reg["id"], RegistrationStatus.ASSIGNED)
        return len(assignments)
