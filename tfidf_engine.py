from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from app.models import Recipe

if TYPE_CHECKING:
    from sklearn.feature_extraction.text import TfidfVectorizer


def _recipe_ingredient_text(recipe: Recipe) -> str:
    try:
        arr = json.loads(recipe.ingredients_json)
        if isinstance(arr, list):
            parts = []
            for x in arr:
                if isinstance(x, dict) and x.get("name"):
                    parts.append(str(x["name"]).lower())
            return " ".join(parts)
    except json.JSONDecodeError:
        pass
    return (recipe.name or "").lower()


def _token_prep(s: str) -> str:
    return re.sub(r"[^\w\s]", " ", s.lower())


@dataclass
class TfidfRecipeIndex:
    recipes: list[Recipe]
    matrix: np.ndarray
    vectorizer: Any

    def pantry_scores(self, pantry_item_names: list[str]) -> list[tuple[Recipe, float]]:
        from sklearn.metrics.pairwise import cosine_similarity

        if not self.recipes or self.matrix.size == 0:
            return []
        q_text = _token_prep(" ".join(pantry_item_names))
        q_vec = self.vectorizer.transform([q_text])
        sims = cosine_similarity(q_vec, self.matrix).ravel()
        order = np.argsort(-sims)
        return [(self.recipes[i], float(sims[i])) for i in order if sims[i] > 0]

    def similar_recipes(self, recipe: Recipe, top_k: int = 5) -> list[tuple[Recipe, float]]:
        from sklearn.metrics.pairwise import cosine_similarity

        ids = [r.id for r in self.recipes]
        if not self.recipes or recipe.id not in ids:
            return []
        idx = ids.index(recipe.id)
        row = self.matrix[idx : idx + 1]
        sims = cosine_similarity(row, self.matrix).ravel()
        sims[idx] = -1.0
        order = np.argsort(-sims)
        out: list[tuple[Recipe, float]] = []
        for i in order[:top_k]:
            if sims[i] <= 0:
                break
            out.append((self.recipes[i], float(sims[i])))
        return out


def build_recipe_index(recipes: list[Recipe]) -> TfidfRecipeIndex:
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [_token_prep(_recipe_ingredient_text(r) + " " + (r.name or "").lower()) for r in recipes]
    if not texts or all(not t.strip() for t in texts):
        return TfidfRecipeIndex(recipes=list(recipes), matrix=np.array([]).reshape(0, 0), vectorizer=TfidfVectorizer())
    vectorizer = TfidfVectorizer(max_features=2048, ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(texts)
    return TfidfRecipeIndex(recipes=list(recipes), matrix=matrix, vectorizer=vectorizer)
