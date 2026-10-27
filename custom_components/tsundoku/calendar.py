"""Calendar for Tsundoku."""

import json
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TsundokuRuntimeData
from .attributes import release_attributes
from .const import CALENDAR_KEY, CONF_CALENDAR_IDS, DOMAIN
from .coordinator import TsundokuCoordinator
from .entity import TsundokuSystemEntity
from .models import ReleaseLine, Volume

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tsundoku calendar, if any release line is in it."""
    if entry.options.get(CONF_CALENDAR_IDS):
        runtime_data: TsundokuRuntimeData = entry.runtime_data
        async_add_entities([TsundokuCalendar(runtime_data.coordinator)])


def _build_event(
    release_line: ReleaseLine, volume: Volume, release_date: date
) -> CalendarEvent:
    """Build the all-day event of a volume: the source has dates, not times."""
    description = json.dumps(
        release_attributes(release_line, volume), indent=2, ensure_ascii=False
    )
    return CalendarEvent(
        start=release_date,
        end=release_date + timedelta(days=1),
        summary=release_line.name,
        description=description,
        uid=f"{DOMAIN}-{release_line.tome_id}-{volume.number}",
    )


def _overlaps(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    """Return True if an all-day event overlaps the requested time range."""
    event_start = dt_util.start_of_local_day(event.start)
    event_end = dt_util.start_of_local_day(event.end)
    return event_start < end and event_end > start


class TsundokuCalendar(
    TsundokuSystemEntity,
    CoordinatorEntity[TsundokuCoordinator],
    CalendarEntity,
):
    """The upcoming volumes of every release line that is in the calendar.

    One all-day event per volume with an exact release date. The title of an
    event is the manga name; everything else is in its description, as JSON.
    Volumes dated to a month or a year only have no event, and the past is never
    listed.
    """

    # The calendar is the main entity of the Tsundoku device and takes its name.
    _attr_name = None
    _attr_translation_key = CALENDAR_KEY
    _attr_should_poll = False
    # The description repeats the release metadata: no need to record it.
    _unrecorded_attributes = frozenset({"description"})

    def __init__(self, coordinator: TsundokuCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = CALENDAR_KEY

    def _events(self) -> list[CalendarEvent]:
        """Return the events from today on, in release order."""
        today = dt_util.now().date()
        events = [
            _build_event(tracked.release_line, volume, volume.release_date)
            for tracked in (self.coordinator.data or {}).values()
            for volume in tracked.calendar_volumes
            if volume.release_date is not None and volume.release_date >= today
        ]
        events.sort(key=lambda event: (event.start, event.summary, event.uid or ""))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the ongoing or next event."""
        events = self._events()
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the events that overlap a time range."""
        return [
            event for event in self._events() if _overlaps(event, start_date, end_date)
        ]
