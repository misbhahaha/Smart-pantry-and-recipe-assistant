"""Ingredient substitution groups."""

SUBSTITUTION_GROUPS = [
    {"butter", "margarine", "ghee", "coconut oil"},
    {"olive oil", "vegetable oil", "canola oil", "sunflower oil"},
    {"milk", "oat milk", "almond milk", "soy milk"},
    {"cream", "coconut cream", "heavy cream"},
    {"rice", "cauliflower rice", "quinoa"},
    {"white sugar", "brown sugar", "honey", "maple syrup"},
    {"chicken breast", "turkey breast", "tofu"},
    {"beef", "lamb", "mushrooms"},
    {"onion", "shallot", "leek"},
    {"garlic", "garlic powder"},
    {"lemon", "lime", "vinegar"},
    {"parsley", "cilantro", "basil"},
    {"cheddar", "mozzarella", "parmesan", "vegan cheese"},
    {"egg", "flax egg", "chia egg"},
    {"flour", "almond flour", "gluten-free flour"},
    {"soy sauce", "tamari", "coconut aminos"},
]

_NAME_TO_GROUP: dict[str, frozenset[str]] = {}


def _norm(s: str) -> str:
    return s.strip().lower()


def _build_maps():
    global _NAME_TO_GROUP
    if _NAME_TO_GROUP:
        return
    for group in SUBSTITUTION_GROUPS:
        frozen = frozenset(_norm(x) for x in group)
        for name in group:
            _NAME_TO_GROUP[_norm(name)] = frozen


def equivalent_names(name: str) -> frozenset[str]:
    _build_maps()
    n = _norm(name)
    return _NAME_TO_GROUP.get(n, frozenset({n}))


def pantry_covers_need(pantry_normalized: set[str], need: str) -> bool:
    need_set = equivalent_names(need)
    for p in pantry_normalized:
        if p in need_set:
            return True
        p_set = equivalent_names(p)
        if need_set & p_set:
            return True
    return False


def substitution_hint(ingredient: str) -> list[str]:
    _build_maps()
    n = _norm(ingredient)
    group = _NAME_TO_GROUP.get(n)
    if not group:
        return []
    return sorted(x for x in group if x != n)
