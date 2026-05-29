"""Canonical crop keys used by backend profile, classifier, and alert logic."""
from typing import Literal

CropKey = Literal["rice", "soybeans", "poultry"]

CROP_RICE: CropKey = "rice"
CROP_SOYBEANS: CropKey = "soybeans"
CROP_POULTRY: CropKey = "poultry"

CROP_KEYS: tuple[CropKey, ...] = (CROP_RICE, CROP_SOYBEANS, CROP_POULTRY)
CROP_NAMESPACES: dict[CropKey, str] = {
    CROP_RICE: "rice",
    CROP_SOYBEANS: "soybeans",
    CROP_POULTRY: "poultry",
}

_CROP_ALIASES = {
    "soybean": CROP_SOYBEANS,
}


def canonical_crop(value: str) -> str:
    """Return canonical crop key, preserving unknown values for validation callers."""
    return _CROP_ALIASES.get(value, value)

