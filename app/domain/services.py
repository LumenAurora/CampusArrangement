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
    elif mode == AllocationMode.POINTS:
        # 意愿点模式：按 points 降序优先，同 points 级别随机抽签（公平）。
        # 用一次性 shuffle 给每个 reg 一个随机 nonce，再按 (-points, nonce) 排序，
        # 保证同级别内公平随机，且高 points 严格优先。
        rng = rng or random.Random()
        # 先生成随机 nonce，避免在 sort key 里反复调用 rng（不稳定）
        nonces = {r.id: rng.random() for r in regs}
        sorted_regs = sorted(regs, key=lambda r: (-r.points, nonces[r.id]))
    else:
        # Lower priority number = higher priority (priority 1 > priority 10)
        sorted_regs = sorted(regs, key=lambda r: (r.priority, r.created_at))

    # 第一轮：按用户选择的slot分配
    unassigned: list[Registration] = []
    for reg in sorted_regs:
        if reg.user_id in assigned_users:
            continue
        capacity = slot_map.get(reg.slot_id)
        if not capacity or capacity.remaining <= 0:
            unassigned.append(reg)
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

    # 第二轮：调剂——将未分配用户分配到同活动中仍有余量的slot
    # 优先尝试用户原选slot（可能容量已释放），再分配到其他同活动slot
    if unassigned:
        # 收集同活动中仍有余量的slot（排除用户原选的已满slot）
        available_slots = [s for s in slot_map.values() if s.remaining > 0]
        available_slots.sort(key=lambda s: s.remaining, reverse=True)
        for reg in unassigned:
            if reg.user_id in assigned_users:
                continue
            # 优先尝试用户原选slot
            original = slot_map.get(reg.slot_id)
            if original and original.remaining > 0:
                assignments.append(
                    ScheduleResult.create(
                        activity_id=reg.activity_id,
                        user_id=reg.user_id,
                        slot_id=original.slot_id,
                    )
                )
                assigned_users.add(reg.user_id)
                slot_map[original.slot_id] = SlotCapacity(slot_id=original.slot_id, remaining=original.remaining - 1)
                # 从available_slots中同步更新
                for i, s in enumerate(available_slots):
                    if s.slot_id == original.slot_id:
                        available_slots[i] = slot_map[original.slot_id]
                        break
                continue
            # 原选slot已满，分配到同活动的其他有余量slot
            for i, slot in enumerate(available_slots):
                if slot.remaining <= 0:
                    continue
                # 不分配到用户原选的已满slot（已在上面处理过）
                if slot.slot_id == reg.slot_id:
                    continue
                assignments.append(
                    ScheduleResult.create(
                        activity_id=reg.activity_id,
                        user_id=reg.user_id,
                        slot_id=slot.slot_id,
                    )
                )
                assigned_users.add(reg.user_id)
                available_slots[i] = SlotCapacity(slot_id=slot.slot_id, remaining=slot.remaining - 1)
                break

    return assignments
