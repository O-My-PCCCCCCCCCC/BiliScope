from __future__ import annotations

from app.scheduler import start_scheduler


def test_scheduler_registers_jobs():
    sched = start_scheduler()
    try:
        jobs = {j.id for j in sched.get_jobs()}
        assert {"sync", "invalid", "updates"} <= jobs
    finally:
        sched.shutdown(wait=False)


def test_scheduler_idempotent():
    s1 = start_scheduler()
    s2 = start_scheduler()
    try:
        assert s1 is s2
    finally:
        s1.shutdown(wait=False)
