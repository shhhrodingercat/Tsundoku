from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TsundokuRuntimeData
from .coordinator import TsundokuCoordinator
from .entity import TsundokuEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tsundoku sensors."""
    runtime_data: TsundokuRuntimeData = entry.runtime_data
    coordinator: TsundokuCoordinator = runtime_data.coordinator

    entities: list[SensorEntity] = []

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


class TsundokuNextVolumeSensor(
    TsundokuEntity,
    SensorEntity,
):
    """Sensor for the next volume number."""

    _attr_translation_key = "next_volume"

    @property
    def _entity_suffix(self) -> str:
        return "next_volume"

    @property
    def native_value(self) -> int | None:
        volume = self._tracked.next_volume
        return volume.number if volume else None


class TsundokuNextReleaseSensor(
    TsundokuEntity,
    SensorEntity,
):
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


class TsundokuLatestVolumeSensor(
    TsundokuEntity,
    SensorEntity,
):
    """Sensor for the latest published volume number."""

    _attr_translation_key = "latest_volume"

    @property
    def _entity_suffix(self) -> str:
        return "latest_volume"

    @property
    def native_value(self) -> int | None:
        volume = self._tracked.latest_volume
        return volume.number if volume else None


class TsundokuVolumesSensor(
    TsundokuEntity,
    SensorEntity,
):
    """Sensor for the number of published volumes."""

    _attr_translation_key = "volumes"

    @property
    def _entity_suffix(self) -> str:
        return "volumes"

    @property
    def native_value(self) -> int:
        return self._tracked.published_volume_count
