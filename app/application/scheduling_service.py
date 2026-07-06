from __future__ import annotations

import logging

from app.domain.exceptions import ValidationError
from app.domain.models import ActivityStatus, AllocationMode, Notification, RegistrationStatus
from app.domain.services import schedule_registrations
from app.infrastructure.db import transaction
from app.infrastructure.repositories import ActivityRepository, NotificationRepository, RegistrationRepository, ScheduleRepository, TimeSlotRepository

logger = logging.getLogger(__name__)


class SchedulingService:
    def __init__(
        self,
        reg_repo: RegistrationRepository,
        slot_repo: TimeSlotRepository,
        schedule_repo: ScheduleRepository,
        activity_repo: ActivityRepository,
        notification_repo: NotificationRepository | None = None,
    ) -> None:
        self._reg_repo = reg_repo
        self._slot_repo = slot_repo
        self._schedule_repo = schedule_repo
        self._activity_repo = activity_repo
        self._notification_repo = notification_repo

    def run(self, activity_id: str) -> int:
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity["status"] not in (ActivityStatus.CLOSED.value,):
            raise ValidationError("只有已关闭报名的活动可以执行排班")
        allocation_mode = AllocationMode(activity["allocation_mode"])
        allow_multiple = bool(activity.get("allow_multiple_slots", 0))
        notifications: list[Notification] = []
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
            slot_names = {
                slot["id"]: slot.get("name") or slot.get("start_time") or slot["id"]
                for slot in slots
            }
            self._slot_repo.reset_used_counts_for_activity(activity_id, conn=conn)
            self._schedule_repo.clear_for_activity(activity_id, conn=conn)
            slot_assign_count: dict[str, int] = {}
            assigned_slots_by_reg_id: dict[str, str] = {}
            # 通过 registration_id 追踪分配结果，避免调剂场景下 (user_id, slot_id)
            # 不匹配（调剂 slot ≠ 原始 reg.slot_id）导致用户被误标为 NOT_ASSIGNED
            assigned_reg_ids: set[str] = set()
            for reg_id, assignment in assignments:
                self._schedule_repo.create(assignment, conn=conn)
                assigned_reg_ids.add(reg_id)
                assigned_slots_by_reg_id[reg_id] = assignment.slot_id
                slot_assign_count[assignment.slot_id] = slot_assign_count.get(assignment.slot_id, 0) + 1
            for slot_id, count in slot_assign_count.items():
                self._slot_repo.increment_used_count(slot_id, count, conn=conn)
            activity_name = activity.get("name", "活动")
            for reg in registrations:
                # 调剂场景下 reg["id"] 仍能匹配 assigned_reg_ids，标记为 ASSIGNED
                if reg["id"] in assigned_reg_ids:
                    self._reg_repo.update_status(reg["id"], RegistrationStatus.ASSIGNED, conn=conn)
                    slot_id = assigned_slots_by_reg_id.get(reg["id"], reg.get("slot_id", ""))
                    slot_label = slot_names.get(slot_id, slot_id)
                    notifications.append(Notification.create(
                        user_id=reg["user_id"],
                        subject="排班结果",
                        body=f"你已被分配到活动「{activity_name}」的「{slot_label}」。",
                        related_link=activity_id,
                    ))
                else:
                    self._reg_repo.update_status(reg["id"], RegistrationStatus.NOT_ASSIGNED, conn=conn)
                    notifications.append(Notification.create(
                        user_id=reg["user_id"],
                        subject="排班结果",
                        body=f"很遗憾，你本次未被分配到活动「{activity_name}」。",
                        related_link=activity_id,
                    ))
        self._save_notifications(notifications)
        return len(assignments)

    def _save_notifications(self, notifications: list[Notification]) -> None:
        if self._notification_repo is None:
            return
        for notification in notifications:
            try:
                self._notification_repo.create(notification)
            except Exception as exc:  # noqa: BLE001 - 通知失败不应回滚排班主流程
                logger.warning("保存排班结果通知失败: %s", exc)
