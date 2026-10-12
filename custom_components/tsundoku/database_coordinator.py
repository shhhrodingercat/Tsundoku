import logging
from dataclasses import replace

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .database_manager import DatabaseManager
from .database_updater import DatabaseStatus

_LOGGER = logging.getLogger(__name__)


class TsundokuDatabaseCoordinator(
    DataUpdateCoordinator[DatabaseStatus]
):
    """Coordinator for Tsundoku database status."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        database_manager: DatabaseManager,
    ) -> None:
        """Initialize the database status coordinator."""
        self.database_manager = database_manager

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_database",
            config_entry=entry,
            always_update=True,
        )

    async def _async_update_data(self) -> DatabaseStatus:
        """Return a snapshot of the current database status."""
        return replace(self.database_manager.status)

    def refresh_status(self) -> None:
        """Notify entities that the database status has changed."""
        self.async_set_updated_data(
            replace(self.database_manager.status)
        )
