"""State attributes of Tsundoku releases, built from the data models."""

from typing import Any

from .models import ReleaseLine, Volume


def _compact(attributes: dict[str, Any]) -> dict[str, Any]:
    """Drop None and empty values: the source leaves many fields unknown."""
    return {
        key: value
        for key, value in attributes.items()
        if value is not None and value != ""
    }


def _display_date(volume: Volume, catalog: dict[str, Any]) -> str | None:
    """Return a localized ``November 2026`` for a volume dated to a month only."""
    raw_date = volume.release_date_raw
    if (
        volume.release_date is not None
        or volume.release_date_precision != "month"
        or not raw_date
    ):
        return None
    try:
        year_text, month_text = raw_date.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
    except (ValueError, TypeError):
        return raw_date
    months = catalog.get("months", [])
    if 1 <= month <= 12 and len(months) >= 12:
        return f"{months[month - 1]} {year}"
    return raw_date


def release_attributes(
    release_line: ReleaseLine,
    volume: Volume,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one release as a flat dict, for calendar events and actions.

    The date keys are the ones of the Next release sensor attributes. Calendar
    events carry it as JSON in their description, actions return it in
    ``releases``. ``tome_id`` is the release line, ``volume_tome_id`` the volume.
    """
    release_date = volume.release_date
    precision = volume.release_date_precision
    if precision is None and release_date is not None:
        precision = "day"
    raw_date = volume.release_date_raw
    if raw_date is None and release_date is not None:
        raw_date = release_date.isoformat()
    return _compact(
        {
            "series_name": release_line.name,
            "volume_number": volume.number,
            "title": volume.title,
            "release_date": release_date.isoformat() if release_date else None,
            "release_date_precision": precision,
            "release_date_raw": raw_date,
            "release_date_type": volume.release_date_type,
            "release_date_display": _display_date(volume, catalog or {}),
            "isbn13": volume.isbn13,
            "local_name": release_line.local_name,
            "country": release_line.country,
            "language": release_line.language,
            "publisher": release_line.publisher,
            "tome_id": release_line.tome_id,
            "volume_tome_id": volume.tome_id,
        }
    )
