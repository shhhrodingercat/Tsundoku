import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDAR_IDS, CONF_TOME_IDS, DOMAIN
from .database import MangaDatabase
from .models import TrackedReleaseLine


class TsundokuCoordinator(DataUpdateCoordinator[dict[str, TrackedReleaseLine]]):
    """Coordinator for Tsundoku release lines."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        database: MangaDatabase,
    ) -> None:
        self.entry = entry
        self.database = database
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(hours=6),
            config_entry=entry,
        )

    async def _async_update_data(self) -> dict[str, TrackedReleaseLine]:
        """Fetch current data from the local database."""
        tome_ids = self.entry.options.get(CONF_TOME_IDS, self.entry.data[CONF_TOME_IDS])
        calendar_ids = set(self.entry.options.get(CONF_CALENDAR_IDS, []))
        today = dt_util.now().date()
        try:
            return await self.hass.async_add_executor_job(
                load_tracked_release_lines,
                self.database,
                tome_ids,
                today,
                calendar_ids,
            )
        except Exception as err:
            raise UpdateFailed(f"Could not read manga metadata: {err}") from err


def load_tracked_release_lines(
    database: MangaDatabase,
    tome_ids: list[str],
    today: date,
    calendar_ids: set[str] | frozenset[str] = frozenset(),
) -> dict[str, TrackedReleaseLine]:
    """Load the current state of all configured release lines.

    Release lines in ``calendar_ids`` also get the volumes with an exact release
    date from today on, which are the events of the calendar.
    """
    result: dict[str, TrackedReleaseLine] = {}
    for tome_id in tome_ids:
        release_line = database.get_release_line(tome_id)
        if release_line is None:
            continue
        latest_volume = database.get_latest_volume(release_line.id, today)
        next_volume = database.get_next_volume(release_line.id, today)
        published_volume_count = database.get_published_volume_count(
            release_line.id, today
        )
        calendar_volumes = (
            tuple(database.get_dated_volumes(release_line.id, today))
            if tome_id in calendar_ids
            else ()
        )
        result[tome_id] = TrackedReleaseLine(
            release_line=release_line,
            latest_volume=latest_volume,
            next_volume=next_volume,
            published_volume_count=published_volume_count,
            calendar_volumes=calendar_volumes,
        )
    return result
