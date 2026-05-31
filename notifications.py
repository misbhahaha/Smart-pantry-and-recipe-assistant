import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import ExpiryNotification, User
from app.services.household_utils import get_household_for_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ExpiryNotificationOut(BaseModel):
    id: int
    severity: str
    message: str
    created_at: dt.datetime
    pantry_item_id: Optional[int] = None

    class Config:
        from_attributes = True


def _hh(db: Session, user: User):
    hh = get_household_for_user(db, user)
    if not hh:
        raise HTTPException(400, "No household")
    return hh


@router.get("/expiry", response_model=list[ExpiryNotificationOut])
def list_expiry_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hh = get_household_for_user(db, user)
    if not hh:
        return []
    return (
        db.query(ExpiryNotification)
        .filter(ExpiryNotification.household_id == hh.id, ExpiryNotification.dismissed.is_(False))
        .order_by(ExpiryNotification.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/expiry/count")
def expiry_unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hh = get_household_for_user(db, user)
    if not hh:
        return {"count": 0}
    n = (
        db.query(ExpiryNotification)
        .filter(ExpiryNotification.household_id == hh.id, ExpiryNotification.dismissed.is_(False))
        .count()
    )
    return {"count": n}


@router.post("/expiry/{notification_id}/dismiss", response_model=dict)
def dismiss_expiry_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hh = _hh(db, user)
    row = (
        db.query(ExpiryNotification)
        .filter(
            ExpiryNotification.id == notification_id,
            ExpiryNotification.household_id == hh.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Notification not found")
    row.dismissed = True
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("/expiry/dismiss-all", response_model=dict)
def dismiss_all_expiry(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hh = _hh(db, user)
    q = db.query(ExpiryNotification).filter(
        ExpiryNotification.household_id == hh.id,
        ExpiryNotification.dismissed.is_(False),
    )
    n = 0
    for row in q.all():
        row.dismissed = True
        db.add(row)
        n += 1
    db.commit()
    return {"dismissed": n}
