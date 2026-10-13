from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TsundokuRuntimeData
from .coordinator import TsundokuCoordinator
from .database_coordinator import TsundokuDatabaseCoordinator
from .entity import TsundokuEntity, TsundokuSystemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tsundoku sensors."""
    runtime_data: TsundokuRuntimeData = entry.runtime_data
    coordinator = runtime_data.coordinator
    database_coordinator = runtime_data.database_coordinator
    entities: list[SensorEntity] = [
        TsundokuDatabaseStatusSensor(database_coordinator),
        TsundokuDatabaseVersionSensor(database_coordinator),
        TsundokuDatabaseUpdatedSensor(database_coordinator),
        TsundokuLastCheckSensor(database_coordinator),
        TsundokuDatabaseSizeSensor(database_coordinator),
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


class TsundokuDatabaseSensor(
    TsundokuSystemEntity,
    CoordinatorEntity[TsundokuDatabaseCoordinator],
    SensorEntity,
):
    """Base class for database status sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return available database diagnostic attributes."""
        status = self.coordinator.data
        attributes: dict[str, str] = {}
        if status.checksum is not None:
            attributes["checksum"] = status.checksum
        if status.last_error is not None:
            attributes["last_error"] = status.last_error
        return attributes


class TsundokuDatabaseStatusSensor(TsundokuDatabaseSensor):
    """Sensor for the database status."""

    _attr_translation_key = "database_status"
    _attr_icon = "mdi:database-check"

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "database_status"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.status


class TsundokuDatabaseVersionSensor(TsundokuDatabaseSensor):
    """Sensor for the installed database version."""

    _attr_translation_key = "database_version"
    _attr_icon = "mdi:tag-outline"

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "database_version"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.version


class TsundokuDatabaseUpdatedSensor(TsundokuDatabaseSensor):
    """Sensor for the last successful database update."""

    _attr_translation_key = "database_updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "database_updated"

    @property
    def native_value(self) -> datetime | None:
        value = self.coordinator.data.database_updated
        return dt_util.as_utc(value) if value else None


class TsundokuLastCheckSensor(TsundokuDatabaseSensor):
    """Sensor for the last remote database check."""

    _attr_translation_key = "last_check"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "last_check"

    @property
    def native_value(self) -> datetime | None:
        value = self.coordinator.data.last_check
        return dt_util.as_utc(value) if value else None


class TsundokuDatabaseSizeSensor(TsundokuDatabaseSensor):
    """Sensor for the local database size."""

    _attr_translation_key = "database_size"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.MEBIBYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TsundokuDatabaseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "database_size"

    @property
    def native_value(self) -> float | None:
        size = self.coordinator.data.size
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
    """Sensor for the next release date, including month-precision dates."""

    _attr_translation_key = "next_release"
    _attr_device_class = SensorDeviceClass.DATE

    @property
    def _entity_suffix(self) -> str:
        return "next_release"

    @property
    def native_value(self) -> date | None:
        volume = self._tracked.next_volume
        if volume is None:
            return None
        if volume.release_date is not None:
            return volume.release_date
        if volume.release_date_precision == "month" and volume.release_date_raw:
            try:
                return date.fromisoformat(f"{volume.release_date_raw}-01")
            except ValueError:
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the original date and its precision."""
        volume = self._tracked.next_volume
        if volume is None:
            return {}
        attributes: dict[str, str] = {}
        precision = volume.release_date_precision
        if precision is None and volume.release_date is not None:
            precision = "day"
        if precision is not None:
            attributes["release_date_precision"] = precision
        raw_date = volume.release_date_raw
        if raw_date is None and volume.release_date is not None:
            raw_date = volume.release_date.isoformat()
        if raw_date is not None:
            attributes["release_date_raw"] = raw_date
        if volume.release_date_type is not None:
            attributes["release_date_type"] = volume.release_date_type
        return attributes


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
