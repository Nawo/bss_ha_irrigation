"""
Backend i18n helper — loads translations from the frontend locale JSON files.

Allows backend services (e.g. ha_publisher) to use the same translation
files as the frontend, avoiding hardcoded duplicate strings.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Locate the locales directory relative to this file:
#   backend/services/i18n.py  ->  ../../frontend/public/locales/
_LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "locales"

# In-memory cache: { "pl": { "common": {...}, "sensors": {...}, ... }, ... }
_cache: dict[str, dict] = {}


def _load_locale(lang: str) -> dict:
    """Load and cache a locale JSON file."""
    if lang in _cache:
        return _cache[lang]

    path = _LOCALES_DIR / lang / "translation.json"
    if not path.exists():
        logger.warning(f"Locale file not found: {path}, falling back to 'en'")
        if lang != "en":
            return _load_locale("en")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache[lang] = data
        return data
    except Exception as e:
        logger.error(f"Failed to load locale {lang}: {e}")
        return {}


def t(key: str, lang: str = "en") -> str:
    """
    Get a translation by dotted key path.

    Examples:
        t("status.active", "pl")          -> "Aktywne"
        t("status.friendlyName", "en")    -> "Irrigation BSS — Watering Status"
    """
    data = _load_locale(lang)
    parts = key.split(".")
    value = data
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return key  # key not found, return as-is

    if value is None:
        # Fallback to English if key missing in requested language
        if lang != "en":
            return t(key, "en")
        return key

    return str(value)


def clear_cache():
    """Clear the locale cache (e.g. after language change)."""
    _cache.clear()
