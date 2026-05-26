import random
import unittest
from datetime import datetime, timedelta, timezone

from app.domain.models import AllocationMode, Registration, RegistrationStatus, TimeSlot
from app.domain.services import schedule_registrations


class SchedulingTests(unittest.TestCase):
    def test_schedule_respects_priority_and_capacity(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=1)
        slot2 = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=2), capacity=1)

        reg1 = Registration.create(user_id="u1", activity_id="a1", slot_id=slot.id, priority=1)
        reg2 = Registration.create(user_id="u2", activity_id="a1", slot_id=slot.id, priority=2)
        reg3 = Registration.create(user_id="u2", activity_id="a1", slot_id=slot2.id, priority=1)

        results = schedule_registrations([reg2, reg1, reg3], [slot, slot2])
        assigned = {(r.user_id, r.slot_id) for r in results}
        self.assertIn(("u1", slot.id), assigned)
        self.assertIn(("u2", slot2.id), assigned)
        self.assertEqual(len(results), 2)

    def test_first_come_ignores_priority(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=1)
        reg_early = Registration(
            id="r1",
            user_id="u1",
            activity_id="a1",
            slot_id=slot.id,
            priority=3,
            status=RegistrationStatus.PENDING,
            created_at=now,
        )
        reg_late = Registration(
            id="r2",
            user_id="u2",
            activity_id="a1",
            slot_id=slot.id,
            priority=1,
            status=RegistrationStatus.PENDING,
            created_at=now + timedelta(minutes=1),
        )
        results = schedule_registrations([reg_late, reg_early], [slot], mode=AllocationMode.FIRST_COME)
        self.assertEqual(results[0].user_id, "u1")

    def test_lottery_assigns_with_capacity(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=2)
        regs = [
            Registration(
                id=f"r{i}",
                user_id=f"u{i}",
                activity_id="a1",
                slot_id=slot.id,
                priority=1,
                status=RegistrationStatus.PENDING,
                created_at=now + timedelta(minutes=i),
            )
            for i in range(5)
        ]
        rng = random.Random(42)
        results = schedule_registrations(regs, [slot], mode=AllocationMode.LOTTERY, rng=rng)
        self.assertEqual(len(results), 2)
        self.assertEqual(len({r.user_id for r in results}), 2)


if __name__ == "__main__":
    unittest.main()
