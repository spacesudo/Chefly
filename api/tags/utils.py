import re

STARTER_TAGS = [
    "recipe",
    "tip",
    "question",
    "baking",
    "dessert",
    "breakfast",
    "quick",
    "healthy",
    "vegan",
    "vegetarian",
    "meal-prep",
    "budget",
    "grilling",
    "street-food",
    "technique",
]

MAX_TAGS_PER_POST = 10
MAX_TAG_LENGTH = 30

_SEPARATORS = re.compile(r"[\s_]+")
_INVALID_CHARS = re.compile(r"[^a-z0-9-]+")
_REPEATED_DASHES = re.compile(r"-{2,}")


def normalize_tag(raw: str) -> str:
    """'#Meal Prep' -> 'meal-prep'. Returns '' if nothing usable remains."""
    tag = raw.strip().lstrip("#").lower()
    tag = _SEPARATORS.sub("-", tag)
    tag = _INVALID_CHARS.sub("", tag)
    return _REPEATED_DASHES.sub("-", tag).strip("-")


def normalize_tags(raw_tags: list[str]) -> list[str]:
    tags = list(dict.fromkeys(t for t in map(normalize_tag, raw_tags) if t))
    if len(tags) > MAX_TAGS_PER_POST:
        raise ValueError(f"A post can have at most {MAX_TAGS_PER_POST} tags")
    too_long = [t for t in tags if len(t) > MAX_TAG_LENGTH]
    if too_long:
        raise ValueError(f"Tags must be at most {MAX_TAG_LENGTH} characters: {', '.join(too_long)}")
    return tags
