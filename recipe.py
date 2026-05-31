from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RecipeOut(BaseModel):
    id: int
    name: str
    cuisine: str
    prep_minutes: int
    calories_per_serving: int
    servings: int
    image_url: str

    class Config:
        from_attributes = True


class CookingGuideStepOut(BaseModel):
    """One Spoonacular analyzed step: what to do, which ingredients, which equipment."""

    number: int
    instruction: str
    ingredients: List[str] = Field(default_factory=list)
    equipment: List[str] = Field(default_factory=list)


class RecipeDetailOut(RecipeOut):
    instructions: str
    ingredients: List[Dict[str, Any]]
    diet_tags: List[str]
    health_notes: List[str]
    # Present when the client sends ?servings= on GET /recipes/{id}
    ingredients_scaled: Optional[List[Dict[str, Any]]] = None
    scaled_to_servings: Optional[int] = None
    # Spoonacular analyzed steps (cached); complements catalog text.
    structured_steps: Optional[List[str]] = None
    step_source: Optional[str] = None
    # Same source: per-step ingredients & equipment from Spoonacular analyzedInstructions.
    cooking_guide_steps: Optional[List[CookingGuideStepOut]] = None
