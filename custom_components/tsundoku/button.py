import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TsundokuRuntimeData
from .entity import TsundokuSystemEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tsundoku database controls."""
    runtime_data: TsundokuRuntimeData = entry.runtime_data
    async_add_entities([TsundokuUpdateDatabaseButton(runtime_data)])


class TsundokuUpdateDatabaseButton(TsundokuSystemEntity, ButtonEntity):
    """Button to check for and install a database update."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "update_database"
    _attr_icon = "mdi:database-sync"
    _attr_should_poll = False

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        self.runtime_data = runtime_data
        self._attr_unique_id = "update_database"

    async def async_press(self) -> None:
        """Check for database updates when pressed."""
        manager = self.runtime_data.database_manager
        try:
            updated = await manager.async_check_for_update()
            if updated:
                await self.runtime_data.coordinator.async_request_refresh()
                _LOGGER.info("Tsundoku database updated successfully")
            else:
                _LOGGER.info("Tsundoku database is already up to date")
        except Exception as err:
            _LOGGER.exception("Manual Tsundoku database update failed")
            raise HomeAssistantError(
                "Tsundoku could not update the database; check the integration logs"
            ) from err
        finally:
            self.runtime_data.database_coordinator.refresh_status()
