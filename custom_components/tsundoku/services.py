"""Actions of Tsundoku."""

from collections import Counter
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .attributes import release_attributes
from .const import (
    ATTR_DAYS,
    ATTR_LIMIT,
    ATTR_MONTH,
    ATTR_START_DATE,
    DEFAULT_RELEASE_DAYS,
    DEFAULT_UPCOMING_LIMIT,
    DOMAIN,
    MAX_RELEASE_DAYS,
    MAX_UPCOMING_LIMIT,
    SERVICE_GET_MONTH_RELEASES,
    SERVICE_GET_RELEASES,
    SERVICE_GET_UPCOMING,
)
from .database import MangaDatabase
from .models import ReleaseLine, Volume

GET_RELEASES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_START_DATE): cv.date,
        vol.Optional(ATTR_DAYS, default=DEFAULT_RELEASE_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_RELEASE_DAYS)
        ),
    }
)

GET_UPCOMING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_LIMIT, default=DEFAULT_UPCOMING_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_UPCOMING_LIMIT)
        ),
    }
)

GET_MONTH_RELEASES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_MONTH): cv.matches_regex(r"^\d{4}-(0[1-9]|1[0-2])$"),
    }
)

type Release = tuple[ReleaseLine, Volume]


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions of Tsundoku."""
    for name, handler, schema in (
        (SERVICE_GET_RELEASES, _async_get_releases, GET_RELEASES_SCHEMA),
        (SERVICE_GET_UPCOMING, _async_get_upcoming, GET_UPCOMING_SCHEMA),
        (
            SERVICE_GET_MONTH_RELEASES,
            _async_get_month_releases,
            GET_MONTH_RELEASES_SCHEMA,
        ),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )


def _loaded_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the loaded config entry, or fail if Tsundoku is not loaded."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return entries[0]


def _tracked_lines(entry: ConfigEntry) -> list[ReleaseLine]:
    return [
        tracked.release_line for tracked in entry.runtime_data.coordinator.data.values()
    ]


def _release_order(release: Release) -> tuple[date, str, str, int]:
    """Sort by day, then release line (name, then id), then volume.

    Volumes dated to a month only come after the ones with an exact day.
    """
    release_line, volume = release
    return (
        volume.release_date or date.max,
        release_line.name.casefold(),
        release_line.tome_id,
        volume.number,
    )


def _load_dated(
    database: MangaDatabase,
    lines: list[ReleaseLine],
    start: date,
    end: date | None,
    limit: int | None = None,
) -> list[Release]:
    """Read the volumes with an exact date from ``start`` up to ``end``."""
    releases = [
        (line, volume)
        for line in lines
        for volume in database.get_dated_volumes(line.id, start, end, limit)
    ]
    releases.sort(key=_release_order)
    return releases


def _load_month(
    database: MangaDatabase, lines: list[ReleaseLine], month: str
) -> list[Release]:
    """Read the volumes of a month, with or without an exact day."""
    releases = [
        (line, volume)
        for line in lines
        for volume in database.get_month_volumes(line.id, month)
    ]
    releases.sort(key=_release_order)
    return releases


def _edition(release_line: ReleaseLine) -> str:
    """Describe the edition of a release line, for example ``IT · Star Comics``."""
    parts = [
        release_line.country.upper() if release_line.country else None,
        release_line.publisher,
    ]
    edition = " · ".join(part for part in parts if part)
    return edition or release_line.language or ""


def _titles(releases: list[Release]) -> list[str]:
    """Return the manga titles of the releases, once each, ready for a message.

    The title is the manga name; the edition is added only when two different
    release lines in the result share a name, for example an Italian and a
    Japanese edition.
    """
    lines: dict[str, ReleaseLine] = {}
    for release_line, _ in releases:
        lines.setdefault(release_line.tome_id, release_line)
    names = Counter(line.name.casefold() for line in lines.values())
    titles = []
    for line in lines.values():
        edition = _edition(line)
        if names[line.name.casefold()] > 1 and edition:
            titles.append(f"{line.name} ({edition})")
        else:
            titles.append(line.name)
    return titles


def _response(releases: list[Release], catalog: dict[str, Any]) -> ServiceResponse:
    return {
        "count": len(releases),
        "titles": _titles(releases),
        "releases": [
            release_attributes(line, volume, catalog) for line, volume in releases
        ],
    }


async def _async_get_releases(call: ServiceCall) -> ServiceResponse:
    """Return the volumes releasing in a range of days."""
    entry = _loaded_entry(call.hass)
    start: date = call.data.get(ATTR_START_DATE) or dt_util.now().date()
    end = start + timedelta(days=call.data[ATTR_DAYS])
    releases = await call.hass.async_add_executor_job(
        _load_dated,
        entry.runtime_data.coordinator.database,
        _tracked_lines(entry),
        start,
        end,
    )
    return _response(releases, entry.runtime_data.locale_catalog)


async def _async_get_upcoming(call: ServiceCall) -> ServiceResponse:
    """Return the next volumes to release, from today on."""
    entry = _loaded_entry(call.hass)
    limit: int = call.data[ATTR_LIMIT]
    releases = await call.hass.async_add_executor_job(
        _load_dated,
        entry.runtime_data.coordinator.database,
        _tracked_lines(entry),
        dt_util.now().date(),
        None,
        limit,
    )
    return _response(releases[:limit], entry.runtime_data.locale_catalog)


async def _async_get_month_releases(call: ServiceCall) -> ServiceResponse:
    """Return the volumes releasing in a month, even without an exact day."""
    entry = _loaded_entry(call.hass)
    month: str = call.data.get(ATTR_MONTH) or dt_util.now().strftime("%Y-%m")
    releases = await call.hass.async_add_executor_job(
        _load_month,
        entry.runtime_data.coordinator.database,
        _tracked_lines(entry),
        month,
    )
    return _response(releases, entry.runtime_data.locale_catalog)
