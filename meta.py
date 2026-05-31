from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User
from app.services.substitutions import SUBSTITUTION_GROUPS

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/substitutions", response_model=list[list[str]])
def substitution_groups(user: User = Depends(get_current_user)):
    return [sorted(g) for g in SUBSTITUTION_GROUPS]
