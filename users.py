import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models import DailyCalorieEntry, HouseholdMember, User
from app.schemas.auth import HouseholdOut, UserOut
from app.services.household_utils import get_household_for_user, parse_json_list

router = APIRouter(prefix="/users", tags=["users"])


def _user_out(u: User) -> UserOut:
    cm = (getattr(u, "cooking_mode", None) or "solo").strip().lower()
    if cm not in ("solo", "family"):
        cm = "solo"
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        dietary_requirements=parse_json_list(u.dietary_requirements),
        health_conditions=parse_json_list(u.health_conditions),
        daily_calorie_target=u.daily_calorie_target,
        ai_preferences=getattr(u, "ai_preferences", None),
        favorite_cuisines=parse_json_list(getattr(u, "favorite_cuisines", None) or "[]"),
        cooking_mode=cm,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.get("/me/household", response_model=Optional[HouseholdOut])
def my_household(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hh = get_household_for_user(db, user)
    if not hh:
        return None
    return HouseholdOut(id=hh.id, name=hh.name, invite_code=hh.invite_code)


class HouseholdUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.patch("/me/household", response_model=HouseholdOut)
def update_household(
    body: HouseholdUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hh = get_household_for_user(db, user)
    if not hh:
        raise HTTPException(400, "No household linked to this account.")
    membership = (
        db.query(HouseholdMember)
        .filter(HouseholdMember.household_id == hh.id, HouseholdMember.user_id == user.id)
        .first()
    )
    if not membership or (membership.role or "").lower() != "owner":
        raise HTTPException(403, "Only the household owner can rename the family plan.")
    hh.name = body.name.strip()[:120]
    db.add(hh)
    db.commit()
    db.refresh(hh)
    return HouseholdOut(id=hh.id, name=hh.name, invite_code=hh.invite_code)


class ProfileUpdate(BaseModel):
    dietary_requirements: list[str] = Field(default_factory=list)
    health_conditions: list[str] = Field(default_factory=list)
    daily_calorie_target: Optional[int] = None
    ai_preferences: Optional[str] = None
    favorite_cuisines: list[str] = Field(default_factory=list)
    cooking_mode: Optional[str] = None  # "solo" | "family"


@router.patch("/me/profile", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.dietary_requirements = json.dumps(body.dietary_requirements)
    user.health_conditions = json.dumps(body.health_conditions)
    user.daily_calorie_target = body.daily_calorie_target
    if body.ai_preferences is not None:
        user.ai_preferences = body.ai_preferences.strip() or None
    user.favorite_cuisines = json.dumps(body.favorite_cuisines)
    if body.cooking_mode is not None:
        cm = body.cooking_mode.strip().lower()
        if cm not in ("solo", "family"):
            raise HTTPException(400, 'cooking_mode must be "solo" or "family"')
        user.cooking_mode = cm
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


@router.patch("/me/password")
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.add(user)
    db.commit()
    return {"ok": True}


class CalorieLogCreate(BaseModel):
    entry_date: date
    calories: int
    notes: Optional[str] = None


class CalorieLogOut(BaseModel):
    id: int
    entry_date: date
    calories: int
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("/me/calories", response_model=list[CalorieLogOut])
def list_calories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(DailyCalorieEntry)
        .filter(DailyCalorieEntry.user_id == user.id)
        .order_by(DailyCalorieEntry.entry_date.desc())
        .limit(120)
        .all()
    )


@router.delete("/me/calories/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calorie_entry(
    entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = (
        db.query(DailyCalorieEntry)
        .filter(DailyCalorieEntry.id == entry_id, DailyCalorieEntry.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Calorie entry not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/calories", response_model=CalorieLogOut)
def log_calories(body: CalorieLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.calories < 1 or body.calories > 50000:
        raise HTTPException(400, "calories must be between 1 and 50000")
    row = DailyCalorieEntry(user_id=user.id, entry_date=body.entry_date, calories=body.calories, notes=body.notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
