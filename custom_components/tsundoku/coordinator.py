import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .database import MangaDatabase
from .models import TrackedReleaseLine


class TsundokuCoordinator(
    DataUpdateCoordinator[dict[str, TrackedReleaseLine]]
):
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

    async def _async_update_data(
        self,
    ) -> dict[str, TrackedReleaseLine]:
        """Fetch current data from the local database."""
        tome_ids = self.entry.data["tome_ids"]
        today = dt_util.now().date()

        return await self.hass.async_add_executor_job(
            load_tracked_release_lines,
            self.database,
            tome_ids,
            today,
        )


def load_tracked_release_lines(
    database: MangaDatabase,
    tome_ids: list[str],
    today: date,
) -> dict[str, TrackedReleaseLine]:
    """Load the current state of all configured release lines."""
    result: dict[str, TrackedReleaseLine] = {}

    for tome_id in tome_ids:
        release_line = database.get_release_line(tome_id)

        if release_line is None:
            continue

        latest_volume = database.get_latest_volume(
            release_line.id,
            today,
        )
        next_volume = database.get_next_volume(
            release_line.id,
            today,
        )
        published_volume_count = database.get_published_volume_count(
            release_line.id,
            today,
        )

        result[tome_id] = TrackedReleaseLine(
            release_line=release_line,
            latest_volume=latest_volume,
            next_volume=next_volume,
            published_volume_count=published_volume_count,
        )

    return result
