import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)

from .const import CALENDAR_KEY, CONF_CALENDAR_IDS, DOMAIN
from .coordinator import TsundokuCoordinator
from .database import MangaDatabase
from .database_coordinator import TsundokuDatabaseCoordinator
from .database_manager import DatabaseManager
from .localization import load_locale_catalog
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class TsundokuRuntimeData:
    """Runtime data for Tsundoku."""

    database_manager: DatabaseManager
    database_coordinator: TsundokuDatabaseCoordinator
    coordinator: TsundokuCoordinator
    locale_catalog: dict[str, Any]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tsundoku integration and register its actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Set up Tsundoku from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)
    database_manager = DatabaseManager(
        hass,
        hass.config.path("tsundoku"),
        session,
    )

    try:
        await database_manager.async_initialize()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Could not initialize Tsundoku database: {err}"
        ) from err

    # Load display translations off the event loop and retain them in memory.
    locale_catalog = await hass.async_add_executor_job(
        load_locale_catalog, hass.config.language
    )

    database_coordinator = TsundokuDatabaseCoordinator(
        hass, entry, database_manager
    )
    await database_coordinator.async_config_entry_first_refresh()

    database = MangaDatabase(database_manager.database_path)
    coordinator = TsundokuCoordinator(hass, entry, database)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = TsundokuRuntimeData(
        database_manager=database_manager,
        database_coordinator=database_coordinator,
        coordinator=coordinator,
        locale_catalog=locale_catalog,
    )

    async def async_update_database(_now=None) -> None:
        """Check for metadata updates without blocking integration setup."""
        try:
            updated = await database_manager.async_check_for_update()
            if updated:
                await coordinator.async_request_refresh()
        except Exception:
            _LOGGER.exception("Error checking for Tsundoku database updates")
        finally:
            database_coordinator.refresh_status()

    async def async_refresh_manga_at_midnight(_now) -> None:
        """Recalculate date-based sensors after the local date changes.

        A volume is the next one through its release day and the latest from the
        day after, so this is what moves the sensors on.
        """
        await coordinator.async_request_refresh()

    remove_database_update_listener = async_track_time_interval(
        hass, async_update_database, timedelta(hours=6)
    )
    entry.async_on_unload(remove_database_update_listener)

    remove_midnight_listener = async_track_time_change(
        hass, async_refresh_manga_at_midnight, hour=0, minute=0, second=5
    )
    entry.async_on_unload(remove_midnight_listener)

    _async_remove_stale_calendars(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Remote update check runs after setup so GitHub latency cannot delay loading.
    entry.async_create_background_task(
        hass, async_update_database(), "Tsundoku database update"
    )
    return True


def _async_remove_stale_calendars(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> None:
    """Remove the calendar entity when no release line is in the calendar."""
    if entry.options.get(CONF_CALENDAR_IDS):
        return
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == Platform.CALENDAR and entity.unique_id == CALENDAR_KEY:
            registry.async_remove(entity.entity_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Unload Tsundoku."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
