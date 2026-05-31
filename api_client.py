"""HTTP client for Smart Pantry backend API."""

from __future__ import annotations

import os
from typing import Any

import httpx

def _resolve_backend_url() -> str:
    env = os.environ.get("BACKEND_URL", "").strip()
    if env:
        return env.rstrip("/")
    try:
        import streamlit as st

        secret = st.secrets.get("BACKEND_URL", "")
        if secret:
            return str(secret).strip().rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:8000"


DEFAULT_BASE = _resolve_backend_url()


class PantryAPI:
    def __init__(self, base_url: str = DEFAULT_BASE, token: str | None = None):
        self.base = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        household_name: str | None = None,
        join_code: str = "",
    ) -> str:
        body = {
            "email": email,
            "password": password,
            "full_name": full_name,
            "join_code": join_code,
        }
        if household_name is not None:
            body["household_name"] = household_name
        r = httpx.post(
            f"{self.base}/api/v1/auth/register",
            json=body,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def login(self, email: str, password: str) -> str:
        r = httpx.post(
            f"{self.base}/api/v1/auth/login",
            json={"email": email, "password": password},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def me(self) -> dict[str, Any]:
        r = httpx.get(f"{self.base}/api/v1/users/me", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def household(self) -> dict[str, Any] | None:
        r = httpx.get(f"{self.base}/api/v1/users/me/household", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def patch_household(self, name: str) -> dict[str, Any]:
        r = httpx.patch(
            f"{self.base}/api/v1/users/me/household",
            headers=self._headers(),
            json={"name": name.strip()},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def patch_profile(
        self,
        dietary: list[str],
        health: list[str],
        calorie_target: int | None,
        ai_preferences: str | None = None,
        favorite_cuisines: list[str] | None = None,
        cooking_mode: str | None = None,
    ) -> dict:
        body: dict = {
            "dietary_requirements": dietary,
            "health_conditions": health,
            "daily_calorie_target": calorie_target,
        }
        if ai_preferences is not None:
            body["ai_preferences"] = ai_preferences
        if favorite_cuisines is not None:
            body["favorite_cuisines"] = favorite_cuisines
        if cooking_mode is not None:
            body["cooking_mode"] = cooking_mode
        r = httpx.patch(
            f"{self.base}/api/v1/users/me/profile",
            headers=self._headers(),
            json=body,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def change_password(self, current_password: str, new_password: str) -> dict:
        r = httpx.patch(
            f"{self.base}/api/v1/users/me/password",
            headers=self._headers(),
            json={"current_password": current_password, "new_password": new_password},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def pantry_list(self) -> list[dict]:
        r = httpx.get(f"{self.base}/api/v1/pantry", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def pantry_add(self, payload: dict) -> dict:
        r = httpx.post(f"{self.base}/api/v1/pantry", headers=self._headers(), json=payload, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def pantry_delete(self, item_id: int) -> None:
        r = httpx.delete(f"{self.base}/api/v1/pantry/{item_id}", headers=self._headers(), timeout=30.0)
        r.raise_for_status()

    def pantry_from_off(self, barcode: str) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/pantry/from-openfoodfacts",
            headers=self._headers(),
            params={"barcode": barcode},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def pantry_from_mock_barcode(self, barcode: str) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/pantry/from-mock-barcode",
            headers=self._headers(),
            params={"barcode": barcode},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def pantry_nutrition_summary(self) -> dict:
        r = httpx.get(f"{self.base}/api/v1/pantry/nutrition-summary", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def pantry_scan_barcode_image(self, file_bytes: bytes, filename: str) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/pantry/scan/barcode-image",
            headers=self._headers(),
            files={"file": (filename, file_bytes, "image/jpeg")},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def pantry_scan_ingredients_ocr(self, file_bytes: bytes, filename: str) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/pantry/scan/ingredients-ocr",
            headers=self._headers(),
            files={"file": (filename, file_bytes, "image/jpeg")},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()

    def recipes(self, cuisine: str | None = None, search: str | None = None, limit: int = 200) -> list[dict]:
        params: dict[str, str] = {"limit": str(max(1, min(int(limit), 5000)))}
        if cuisine:
            params["cuisine"] = cuisine
        if search and search.strip():
            params["q"] = search.strip()
        r = httpx.get(f"{self.base}/api/v1/recipes", headers=self._headers(), params=params, timeout=90.0)
        r.raise_for_status()
        return r.json()

    def cuisines(self) -> list[str]:
        r = httpx.get(f"{self.base}/api/v1/recipes/cuisines", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def recipe_catalog_health(self) -> dict:
        r = httpx.get(f"{self.base}/api/v1/recipes/catalog-health", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def recipe_images_backfill(self, *, online_search: bool = True, search_cap: int = 50) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/recipes/images/backfill",
            headers=self._headers(),
            params={"online_search": online_search, "search_cap": search_cap},
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json()

    def recipe(self, rid: int, servings: int | None = None) -> dict:
        params: dict[str, str] = {}
        if servings is not None:
            params["servings"] = str(int(servings))
        r = httpx.get(
            f"{self.base}/api/v1/recipes/{rid}",
            headers=self._headers(),
            params=params if params else None,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def recipe_pantry_match(self, rid: int) -> dict:
        r = httpx.get(f"{self.base}/api/v1/recipes/{rid}/pantry-match", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def recommendations_ai(self, limit: int = 12) -> list[dict]:
        r = httpx.get(
            f"{self.base}/api/v1/recommendations/ai",
            headers=self._headers(),
            params={"limit": limit},
            timeout=45.0,
        )
        r.raise_for_status()
        return r.json()

    def recommendations_rules(self, limit: int = 20) -> list[dict]:
        r = httpx.get(
            f"{self.base}/api/v1/recommendations/rules",
            headers=self._headers(),
            params={"limit": limit},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def themealdb_areas(self) -> list[str]:
        r = httpx.get(f"{self.base}/api/v1/imports/themealdb/areas", headers=self._headers(), timeout=30.0)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        return r.json()

    def import_themealdb(self, area: str, limit: int = 15) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/imports/themealdb",
            headers=self._headers(),
            json={"area": area, "limit": limit},
            timeout=120.0,
        )
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"imported": 0, "area": area, "note": "Import endpoint unavailable or no meals found."}
            raise
        return r.json()

    def import_regional_bundles(self, per_cuisine_cap: int = 150) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/imports/themealdb/regional-bundles",
            headers=self._headers(),
            json={"per_cuisine_cap": per_cuisine_cap},
            timeout=900.0,
        )
        r.raise_for_status()
        return r.json()

    def import_csv(self, file_bytes: bytes, filename: str) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/imports/recipes-csv",
            headers=self._headers(),
            files={"file": (filename, file_bytes, "text/csv")},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()

    def import_kaggle_sample(self) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/imports/recipes-kaggle-sample",
            headers=self._headers(),
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()

    def expiry_notifications(self) -> list[dict]:
        r = httpx.get(f"{self.base}/api/v1/notifications/expiry", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def expiry_notification_count(self) -> dict:
        r = httpx.get(f"{self.base}/api/v1/notifications/expiry/count", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def expiry_dismiss(self, notification_id: int) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/notifications/expiry/{notification_id}/dismiss",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def expiry_dismiss_all(self) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/notifications/expiry/dismiss-all",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def shopping_list(self) -> dict:
        r = httpx.get(f"{self.base}/api/v1/shopping", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def shopping_add_item(self, item_name: str, quantity: float = 1.0, unit: str = "each") -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/shopping/items",
            headers=self._headers(),
            json={"item_name": item_name, "quantity": quantity, "unit": unit},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def shopping_from_recipe(
        self,
        recipe_id: int,
        servings: int | None = None,
        *,
        only_ingredient_names: list[str] | None = None,
    ) -> dict:
        body: dict = {"recipe_id": int(recipe_id)}
        if servings is not None:
            body["servings"] = int(servings)
        if only_ingredient_names:
            body["only_ingredient_names"] = [str(n).strip() for n in only_ingredient_names if str(n).strip()]
        r = httpx.post(
            f"{self.base}/api/v1/shopping/from-recipe",
            headers=self._headers(),
            json=body,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def shopping_toggle(self, item_id: int) -> dict:
        r = httpx.patch(
            f"{self.base}/api/v1/shopping/items/{item_id}/toggle",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def shopping_delete_item(self, item_id: int) -> None:
        r = httpx.delete(
            f"{self.base}/api/v1/shopping/items/{item_id}",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()

    def shopping_clear_checked(self) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/shopping/clear-checked",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def shopping_clear_all(self) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/shopping/clear-all",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def substitution_groups(self) -> dict:
        r = httpx.get(f"{self.base}/api/v1/recipes/substitutions", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def log_calories(self, entry_date: str, calories: int, notes: str = "") -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/users/me/calories",
            headers=self._headers(),
            json={"entry_date": entry_date, "calories": calories, "notes": notes or None},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def calories_list(self) -> list[dict]:
        r = httpx.get(f"{self.base}/api/v1/users/me/calories", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def delete_calorie_entry(self, entry_id: int) -> None:
        r = httpx.delete(
            f"{self.base}/api/v1/users/me/calories/{entry_id}",
            headers=self._headers(),
            timeout=30.0,
        )
        if r.status_code == 204:
            return
        r.raise_for_status()
