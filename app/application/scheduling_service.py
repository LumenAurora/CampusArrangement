from __future__ import annotations

from app.domain.exceptions import ValidationError
from app.domain.models import ActivityStatus, AllocationMode, RegistrationStatus
from app.domain.services import schedule_registrations
from app.infrastructure.db import transaction
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
        if activity["status"] not in (ActivityStatus.CLOSED.value,):
            raise ValidationError("只有已关闭报名的活动可以执行排班")
        allocation_mode = AllocationMode(activity["allocation_mode"])
        allow_multiple = bool(activity.get("allow_multiple_slots", 0))
        # Perform all scheduling operations within a single transaction to prevent
        # TOCTOU race conditions (e.g., concurrent scheduling runs).
        with transaction() as conn:
            # Reset NOT_ASSIGNED/ASSIGNED registrations back to PENDING so they can be re-scheduled
            self._reg_repo.reset_for_rescheduling(activity_id, conn=conn)
            registrations = self._reg_repo.list_pending(activity_id, conn=conn)
            slots = self._slot_repo.list_by_activity(activity_id, conn=conn)
            if not registrations:
                # 没有报名记录时也要清空旧排班结果和名额统计，防止数据不一致
                self._slot_repo.reset_used_counts_for_activity(activity_id, conn=conn)
                self._schedule_repo.clear_for_activity(activity_id, conn=conn)
                return 0
            if not slots:
                raise ValidationError("没有可用的时段")
            assignments = schedule_registrations(
                registrations=self._reg_repo.to_models(registrations),
                slots=self._slot_repo.to_models(slots),
                mode=allocation_mode,
                allow_multiple=allow_multiple,
            )
            self._slot_repo.reset_used_counts_for_activity(activity_id, conn=conn)
            self._schedule_repo.clear_for_activity(activity_id, conn=conn)
            slot_assign_count: dict[str, int] = {}
            # 通过 registration_id 追踪分配结果，避免调剂场景下 (user_id, slot_id)
            # 不匹配（调剂 slot ≠ 原始 reg.slot_id）导致用户被误标为 NOT_ASSIGNED
            assigned_reg_ids: set[str] = set()
            for reg_id, assignment in assignments:
                self._schedule_repo.create(assignment, conn=conn)
                assigned_reg_ids.add(reg_id)
                slot_assign_count[assignment.slot_id] = slot_assign_count.get(assignment.slot_id, 0) + 1
            for slot_id, count in slot_assign_count.items():
                self._slot_repo.increment_used_count(slot_id, count, conn=conn)
            for reg in registrations:
                # 调剂场景下 reg["id"] 仍能匹配 assigned_reg_ids，标记为 ASSIGNED
                if reg["id"] in assigned_reg_ids:
                    self._reg_repo.update_status(reg["id"], RegistrationStatus.ASSIGNED, conn=conn)
                else:
                    self._reg_repo.update_status(reg["id"], RegistrationStatus.NOT_ASSIGNED, conn=conn)
        return len(assignments)
