import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)

from .const import DOMAIN
from .coordinator import TsundokuCoordinator
from .database import MangaDatabase
from .database_coordinator import TsundokuDatabaseCoordinator
from .database_manager import DatabaseManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class TsundokuRuntimeData:
    """Runtime data for Tsundoku."""

    database_manager: DatabaseManager
    database_coordinator: TsundokuDatabaseCoordinator
    coordinator: TsundokuCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tsundoku integration."""
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
        """Recalculate date-based sensors after the local date changes."""
        await coordinator.async_request_refresh()

    remove_database_update_listener = async_track_time_interval(
        hass, async_update_database, timedelta(hours=6)
    )
    entry.async_on_unload(remove_database_update_listener)

    remove_midnight_listener = async_track_time_change(
        hass, async_refresh_manga_at_midnight, hour=0, minute=0, second=5
    )
    entry.async_on_unload(remove_midnight_listener)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Remote update check runs after setup so GitHub latency cannot delay loading.
    hass.async_create_task(async_update_database())
    return True


async def async_reload_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> None:
    """Reload Tsundoku after its tracked manga options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Unload Tsundoku."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
