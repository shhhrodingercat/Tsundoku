from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TsundokuCoordinator
from .models import TrackedReleaseLine


class TsundokuEntity(CoordinatorEntity[TsundokuCoordinator]):
    """Base class for manga release-line entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TsundokuCoordinator, tome_id: str) -> None:
        super().__init__(coordinator)
        self.tome_id = tome_id
        tracked = self._tracked
        self._attr_unique_id = f"{tome_id}_{self._entity_suffix}"
        release_line = tracked.release_line
        edition_parts = [release_line.name]
        if release_line.country:
            edition_parts.append(release_line.country.upper())
        if release_line.language:
            edition_parts.append(release_line.language.lower())
        if release_line.publisher:
            edition_parts.append(release_line.publisher)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tome_id)},
            "name": " · ".join(edition_parts),
            "manufacturer": release_line.publisher or "Tsundoku",
            "model": "Manga release line",
        }

    @property
    def available(self) -> bool:
        """Become unavailable if the selected line disappears from the DB."""
        return super().available and self.tome_id in self.coordinator.data

    @property
    def _tracked(self) -> TrackedReleaseLine:
        """Return the tracked release line."""
        return self.coordinator.data[self.tome_id]

    @property
    def _entity_suffix(self) -> str:
        """Return the entity-specific unique ID suffix."""
        raise NotImplementedError


class TsundokuSystemEntity:
    """Base class for entities belonging to the Tsundoku system device."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> dict:
        """Return information about the Tsundoku system device."""
        return {
            "identifiers": {(DOMAIN, "system")},
            "name": "Tsundoku",
            "manufacturer": "Tsundoku",
            "model": "Manga database manager",
        }
