from __future__ import annotations

import json
import secrets

from sqlalchemy.orm import Session

from app.models import Household, HouseholdMember, User


def new_invite_code() -> str:
    return secrets.token_hex(4).upper()


def get_household_for_user(db: Session, user: User) -> Household | None:
    m = db.query(HouseholdMember).filter(HouseholdMember.user_id == user.id).first()
    if not m:
        return None
    return db.query(Household).filter(Household.id == m.household_id).first()


def parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return []
