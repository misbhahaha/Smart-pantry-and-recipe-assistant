from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    full_name: str
    household_name: str = "My Household"
    join_code: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    dietary_requirements: list[str]
    health_conditions: list[str]
    daily_calorie_target: Optional[int]
    ai_preferences: Optional[str] = None
    favorite_cuisines: list[str] = []
    cooking_mode: str = "solo"

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HouseholdOut(BaseModel):
    id: int
    name: str
    invite_code: str

    class Config:
        from_attributes = True
