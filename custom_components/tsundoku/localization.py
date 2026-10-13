import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent / "locales"


def load_locale_catalog(language: str | None) -> dict[str, Any]:
    """Load optional display translations, falling back to English."""
    locale = (language or "en").replace("-", "_").split("_", maxsplit=1)[0].lower()
    for candidate in (locale, "en"):
        path = _LOCALES_DIR / f"{candidate}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}
