from typing import Optional

from pydantic import BaseModel, Field


class RecommendationOut(BaseModel):
    recipe_id: int
    name: str
    cuisine: str
    image_url: str
    ingredient_match_score: float
    ai_score: Optional[float] = None
    reason: str
    model: str
    diet_tags: list[str] = Field(default_factory=list)
