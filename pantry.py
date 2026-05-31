from datetime import date
from typing import Optional

from pydantic import BaseModel


class PantryItemCreate(BaseModel):
    name: str
    quantity: float = 1.0
    unit: str = "each"
    category: str = "general"
    expiration_date: Optional[date] = None
    barcode: Optional[str] = None
    notes: Optional[str] = None


class PantryItemOut(BaseModel):
    id: int
    name: str
    quantity: float
    unit: str
    category: str
    expiration_date: Optional[date]
    barcode: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True
