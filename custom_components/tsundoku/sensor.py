from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TsundokuRuntimeData
from .coordinator import TsundokuCoordinator
from .entity import TsundokuEntity, TsundokuSystemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tsundoku sensors."""
    runtime_data: TsundokuRuntimeData = entry.runtime_data
    coordinator: TsundokuCoordinator = runtime_data.coordinator

    entities: list[SensorEntity] = [
        TsundokuDatabaseStatusSensor(runtime_data),
        TsundokuDatabaseVersionSensor(runtime_data),
        TsundokuDatabaseUpdatedSensor(runtime_data),
        TsundokuLastCheckSensor(runtime_data),
        TsundokuDatabaseSizeSensor(runtime_data),
    ]

    for tome_id in coordinator.data:
        entities.extend(
            (
                TsundokuNextVolumeSensor(coordinator, tome_id),
                TsundokuNextReleaseSensor(coordinator, tome_id),
                TsundokuLatestVolumeSensor(coordinator, tome_id),
                TsundokuVolumesSensor(coordinator, tome_id),
            )
        )

    async_add_entities(entities)


class TsundokuDatabaseSensor(TsundokuSystemEntity, SensorEntity):
    """Base class for database status sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        """Initialize the database sensor."""
        self.runtime_data = runtime_data

    @property
    def extra_state_attributes(self) -> dict:
        """Return database diagnostic attributes."""
        status = self.runtime_data.database_manager.status

        return {
            "checksum": status.checksum,
            "last_error": status.last_error,
        }


class TsundokuDatabaseStatusSensor(TsundokuDatabaseSensor):
    """Sensor for the database status."""

    _attr_translation_key = "database_status"
    _attr_icon = "mdi:database-check"

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        super().__init__(runtime_data)
        self._attr_unique_id = "database_status"

    @property
    def native_value(self) -> str:
        return self.runtime_data.database_manager.status.status


class TsundokuDatabaseVersionSensor(TsundokuDatabaseSensor):
    """Sensor for the installed database version."""

    _attr_translation_key = "database_version"
    _attr_icon = "mdi:tag-outline"

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        super().__init__(runtime_data)
        self._attr_unique_id = "database_version"

    @property
    def native_value(self) -> str | None:
        return self.runtime_data.database_manager.status.version


class TsundokuDatabaseUpdatedSensor(TsundokuDatabaseSensor):
    """Sensor for the last successful database update."""

    _attr_translation_key = "database_updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        super().__init__(runtime_data)
        self._attr_unique_id = "database_updated"

    @property
    def native_value(self):
        value = self.runtime_data.database_manager.status.database_updated
        return dt_util.as_utc(value) if value else None


class TsundokuLastCheckSensor(TsundokuDatabaseSensor):
    """Sensor for the last remote database check."""

    _attr_translation_key = "last_check"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        super().__init__(runtime_data)
        self._attr_unique_id = "last_check"

    @property
    def native_value(self):
        value = self.runtime_data.database_manager.status.last_check
        return dt_util.as_utc(value) if value else None


class TsundokuDatabaseSizeSensor(TsundokuDatabaseSensor):
    """Sensor for the local database size."""

    _attr_translation_key = "database_size"
    _attr_native_unit_of_measurement = "MB"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime_data: TsundokuRuntimeData) -> None:
        super().__init__(runtime_data)
        self._attr_unique_id = "database_size"

    @property
    def native_value(self) -> float | None:
        size = self.runtime_data.database_manager.status.size
        return round(size / (1024 * 1024), 2) if size is not None else None


class TsundokuNextVolumeSensor(TsundokuEntity, SensorEntity):
    """Sensor for the next volume number."""

    _attr_translation_key = "next_volume"

    @property
    def _entity_suffix(self) -> str:
        return "next_volume"

    @property
    def native_value(self) -> int | None:
        volume = self._tracked.next_volume
        return volume.number if volume else None


class TsundokuNextReleaseSensor(TsundokuEntity, SensorEntity):
    """Sensor for the next release date."""

    _attr_translation_key = "next_release"
    _attr_device_class = SensorDeviceClass.DATE

    @property
    def _entity_suffix(self) -> str:
        return "next_release"

    @property
    def native_value(self) -> date | None:
        volume = self._tracked.next_volume
        return volume.release_date if volume else None


class TsundokuLatestVolumeSensor(TsundokuEntity, SensorEntity):
    """Sensor for the latest published volume number."""

    _attr_translation_key = "latest_volume"

    @property
    def _entity_suffix(self) -> str:
        return "latest_volume"

    @property
    def native_value(self) -> int | None:
        volume = self._tracked.latest_volume
        return volume.number if volume else None


class TsundokuVolumesSensor(TsundokuEntity, SensorEntity):
    """Sensor for the number of published volumes."""

    _attr_translation_key = "volumes"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def _entity_suffix(self) -> str:
        return "volumes"

    @property
    def native_value(self) -> int:
        return self._tracked.published_volume_count