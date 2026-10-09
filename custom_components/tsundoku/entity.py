from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TsundokuCoordinator
from .models import TrackedReleaseLine


class TsundokuEntity(CoordinatorEntity[TsundokuCoordinator]):
    """Base entity for Tsundoku."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TsundokuCoordinator,
        tome_id: str,
    ) -> None:
        super().__init__(coordinator)

        self.tome_id = tome_id

        tracked = self._tracked

        self._attr_unique_id = (
            f"{tome_id}_{self._entity_suffix}"
        )

        self._attr_device_info = {
            "identifiers": {(DOMAIN, tome_id)},
            "name": tracked.release_line.name,
            "manufacturer": "Tsundoku",
            "model": "Manga release line",
        }

    @property
    def _tracked(self) -> TrackedReleaseLine:
        """Return the tracked release line."""
        return self.coordinator.data[self.tome_id]

    @property
    def _entity_suffix(self) -> str:
        """Return the entity-specific unique ID suffix."""
        raise NotImplementedError
