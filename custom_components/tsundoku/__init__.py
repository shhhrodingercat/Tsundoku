import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import TsundokuCoordinator
from .database import MangaDatabase
from .database_coordinator import TsundokuDatabaseCoordinator
from .database_manager import DatabaseManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BUTTON,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class TsundokuRuntimeData:
    """Runtime data for Tsundoku."""

    database_manager: DatabaseManager
    database_coordinator: TsundokuDatabaseCoordinator
    coordinator: TsundokuCoordinator
    remove_database_update_listener: Callable[[], None]


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up the Tsundoku integration."""
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Set up Tsundoku from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)

    database_manager = DatabaseManager(
        hass.config.path("tsundoku"),
        session,
    )

    database_existed = database_manager.database_path.is_file()

    await database_manager.async_initialize()

    # Check for updates at startup when a local database already exists.
    if database_existed:
        try:
            await database_manager.async_check_for_update()
        except Exception:
            _LOGGER.exception(
                "Could not check for Tsundoku database updates "
                "during startup"
            )

    database_coordinator = TsundokuDatabaseCoordinator(
        hass,
        entry,
        database_manager,
    )

    await database_coordinator.async_config_entry_first_refresh()

    database = MangaDatabase(database_manager.database_path)

    coordinator = TsundokuCoordinator(
        hass,
        entry,
        database,
    )

    await coordinator.async_config_entry_first_refresh()

    async def async_update_database(_now) -> None:
        """Check for database updates and notify the coordinators."""
        try:
            updated = await database_manager.async_check_for_update()

            if updated:
                await coordinator.async_request_refresh()

        except Exception:
            _LOGGER.exception(
                "Error checking for Tsundoku database updates"
            )

        finally:
            database_coordinator.refresh_status()

    remove_database_update_listener = async_track_time_interval(
        hass,
        async_update_database,
        timedelta(hours=6),
    )

    entry.runtime_data = TsundokuRuntimeData(
        database_manager=database_manager,
        database_coordinator=database_coordinator,
        coordinator=coordinator,
        remove_database_update_listener=(
            remove_database_update_listener
        ),
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Unload Tsundoku."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unloaded:
        entry.runtime_data.remove_database_update_listener()

    return unloaded