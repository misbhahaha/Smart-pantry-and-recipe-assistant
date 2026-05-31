"""APScheduler: background expiry scans."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import SessionLocal
from app.models import ExpiryNotification, PantryItem

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def run_expiry_scan() -> int:
    today = dt.datetime.utcnow().date()
    db = SessionLocal()
    created = 0
    try:
        items: list[PantryItem] = db.query(PantryItem).filter(PantryItem.expiration_date.isnot(None)).all()
        for it in items:
            if not it.expiration_date:
                continue
            days = (it.expiration_date - today).days
            if days < 0:
                sev, msg = "expired", f"Expired: {it.name} (was {it.expiration_date})"
            elif days <= 3:
                sev, msg = "warning", f"Use soon: {it.name} expires {it.expiration_date} ({days}d)"
            elif days <= 7:
                sev, msg = "info", f"Coming up: {it.name} expires {it.expiration_date} ({days}d)"
            else:
                continue
            day_start = dt.datetime.combine(today, dt.time.min)
            exists = (
                db.query(ExpiryNotification)
                .filter(
                    ExpiryNotification.pantry_item_id == it.id,
                    ExpiryNotification.severity == sev,
                    ExpiryNotification.created_at >= day_start,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                ExpiryNotification(
                    household_id=it.household_id,
                    pantry_item_id=it.id,
                    severity=sev,
                    message=msg,
                )
            )
            created += 1
        db.commit()
    except Exception:
        logger.exception("expiry scan failed")
        db.rollback()
    finally:
        db.close()
    return created


def start_scheduler(expiry_interval_minutes: int = 60, on_start: Callable[[], None] | None = None) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler()
    sched.add_job(run_expiry_scan, "interval", minutes=max(15, expiry_interval_minutes), id="expiry_scan")
    sched.start()
    run_expiry_scan()
    if on_start:
        on_start()
    _scheduler = sched
    logger.info("APScheduler started (expiry scan every %s min)", expiry_interval_minutes)
    return sched


def stop_scheduler() -> None:
    """Shut down background jobs when the ASGI process exits (reload, SIGTERM, etc.)."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
    except Exception:
        logger.exception("APScheduler shutdown failed")
    finally:
        _scheduler = None
