from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReleaseLine:
    id: int
    tome_id: str
    name: str
    local_name: str | None
    publisher: str | None
    language: str | None
    country: str | None
    medium: str
    volume_count: int
    status: str | None


@dataclass(frozen=True)
class Volume:
    id: int
    series_id: int
    number: int
    title: str | None
    release_date: date | None
    release_date_precision: str | None
    release_date_type: str | None
    isbn13: str | None
    tome_id: str | None


@dataclass(frozen=True)
class TrackedReleaseLine:
    release_line: ReleaseLine
    latest_volume: Volume | None
    next_volume: Volume | None
    published_volume_count: int
