from typing import Optional

from pydantic import BaseModel, Field


class ShoppingItemOut(BaseModel):
    id: int
    item_name: str
    quantity: float
    unit: str
    is_checked: bool
    source_recipe_id: Optional[int] = None
    source_recipe_name: Optional[str] = None

    class Config:
        from_attributes = True


class ShoppingItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1.0, gt=0, le=100_000)
    unit: str = Field(default="each", max_length=64)


class ShoppingFromRecipeIn(BaseModel):
    recipe_id: int
    servings: Optional[int] = Field(None, ge=1, le=99)
    only_ingredient_names: Optional[list[str]] = Field(
        None,
        description="If set, add only these missing ingredient names (user-selected).",
    )


class ShoppingListOut(BaseModel):
    list_id: int
    name: str
    items: list[ShoppingItemOut]
