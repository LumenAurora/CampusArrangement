from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
from typing import Iterable

from .models import AllocationMode, Registration, ScheduleResult, TimeSlot


@dataclass(frozen=True)
class SlotCapacity:
    slot_id: str
    remaining: int


def schedule_registrations(
    registrations: Iterable[Registration],
    slots: Iterable[TimeSlot],
    mode: AllocationMode = AllocationMode.GREEDY,
    rng: random.Random | None = None,
) -> list[ScheduleResult]:
    slot_map = {slot.id: SlotCapacity(slot_id=slot.id, remaining=slot.capacity) for slot in slots}
    assignments: list[ScheduleResult] = []
    assigned_users: set[str] = set()

    regs = list(registrations)
    if mode == AllocationMode.FIRST_COME:
        sorted_regs = sorted(regs, key=lambda r: r.created_at)
    elif mode == AllocationMode.LOTTERY:
        rng = rng or random.Random()
        sorted_regs = regs[:]
        rng.shuffle(sorted_regs)
    else:
        sorted_regs = sorted(regs, key=lambda r: (r.priority, r.created_at))

    for reg in sorted_regs:
        if reg.user_id in assigned_users:
            continue
        capacity = slot_map.get(reg.slot_id)
        if not capacity or capacity.remaining <= 0:
            continue
        assignments.append(
            ScheduleResult.create(
                activity_id=reg.activity_id,
                user_id=reg.user_id,
                slot_id=reg.slot_id,
            )
        )
        assigned_users.add(reg.user_id)
        slot_map[reg.slot_id] = SlotCapacity(slot_id=capacity.slot_id, remaining=capacity.remaining - 1)

    return assignments
