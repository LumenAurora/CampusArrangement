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
    allow_multiple: bool = False,
) -> list[tuple[str, ScheduleResult]]:
    """排班核心算法。

    返回值：`list[(registration_id, ScheduleResult)]`。
    通过 registration_id 关联原始报名，使上层在标记 ASSIGNED/NOT_ASSIGNED 时
    能正确处理调剂场景（调剂用户的 slot_id 与原始 reg.slot_id 不同，
    若用 (user_id, slot_id) 匹配会误标为 NOT_ASSIGNED）。
    """
    slot_map = {slot.id: SlotCapacity(slot_id=slot.id, remaining=slot.capacity) for slot in slots}
    assignments: list[tuple[str, ScheduleResult]] = []
    # 兼报模式按 (user_id, slot_id) 去重，单报模式按 user_id 全局去重
    assigned_user_slots: set[tuple[str, str]] = set()
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

    # 第一轮：按用户选择的slot分配
    unassigned: list[Registration] = []
    for reg in sorted_regs:
        # 去重检查：兼报模式防止同一用户在同一 slot 重复分配，单报模式防止用户重复分配
        if allow_multiple:
            if (reg.user_id, reg.slot_id) in assigned_user_slots:
                continue
        else:
            if reg.user_id in assigned_users:
                continue
        capacity = slot_map.get(reg.slot_id)
        if not capacity or capacity.remaining <= 0:
            unassigned.append(reg)
            continue
        assignments.append(
            (
                reg.id,
                ScheduleResult.create(
                    activity_id=reg.activity_id,
                    user_id=reg.user_id,
                    slot_id=reg.slot_id,
                ),
            )
        )
        if allow_multiple:
            assigned_user_slots.add((reg.user_id, reg.slot_id))
        else:
            assigned_users.add(reg.user_id)
        slot_map[reg.slot_id] = SlotCapacity(slot_id=capacity.slot_id, remaining=capacity.remaining - 1)

    # 第二轮：调剂——仅单报模式执行，将未分配用户调剂到有余量的slot
    # 兼报模式下用户已主动选择多个 slot，不做调剂避免分配到用户未选的岗位
    # 调剂时仅选择父时段（parent_slot_id 为 None），避免分配到子岗位（如"接待员"等具体职责）
    if unassigned and not allow_multiple:
        available_slots = [s for s in slot_map.values() if s.remaining > 0]
        available_slots.sort(key=lambda s: s.remaining, reverse=True)
        slot_idx = 0
        for reg in unassigned:
            if reg.user_id in assigned_users:
                continue
            while slot_idx < len(available_slots):
                slot = available_slots[slot_idx]
                if slot.remaining <= 0:
                    slot_idx += 1
                    continue
                assignments.append(
                    (
                        reg.id,
                        ScheduleResult.create(
                            activity_id=reg.activity_id,
                            user_id=reg.user_id,
                            slot_id=slot.slot_id,
                        ),
                    )
                )
                assigned_users.add(reg.user_id)
                available_slots[slot_idx] = SlotCapacity(slot_id=slot.slot_id, remaining=slot.remaining - 1)
                break
            else:
                break

    return assignments
