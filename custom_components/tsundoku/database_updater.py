import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from aiohttp import ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant

DATABASE_FILENAME = "manga-metadata.sqlite"
METADATA_FILENAME = "metadata.json"
_LOGGER = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {
    "series": {
        "gcd_series_id", "name", "tome_id", "medium", "local_name",
        "publisher", "language", "country", "volume_count", "status",
    },
    "volumes": {
        "id", "gcd_series_id", "volume_number", "title", "release_date",
        "release_date_precision", "release_date_raw", "release_date_type",
        "isbn13", "tome_id",
    },
    "series_alias": {"gcd_series_id", "alias"},
    "id_redirect": {"old_tome_id", "new_tome_id"},
}


@dataclass
class DatabaseStatus:
    """Current status of the local manga database."""
    status: str
    version: str | None = None
    database_updated: datetime | None = None
    last_check: datetime | None = None
    checksum: str | None = None
    size: int | None = None
    last_error: str | None = None


class DatabaseUpdater:
    """Manage the local Tsundoku database."""

    def __init__(self, hass: HomeAssistant, database_dir: str | Path) -> None:
        self.hass = hass
        self.database_dir = Path(database_dir)
        self.database_path = self.database_dir / DATABASE_FILENAME
        self.metadata_path = self.database_dir / METADATA_FILENAME
        self.status = DatabaseStatus(status="unknown")

    def load_status(self) -> DatabaseStatus:
        """Load persisted database metadata."""
        if not self.metadata_path.exists():
            return self.status
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _LOGGER.warning("Could not read Tsundoku database metadata")
            return self.status
        if not isinstance(data, dict):
            _LOGGER.warning("Tsundoku database metadata has an invalid format")
            return self.status

        status = data.get("status")
        version = data.get("version")
        checksum = data.get("checksum")
        size = data.get("size")
        last_error = data.get("last_error")
        self.status = DatabaseStatus(
            status=status if isinstance(status, str) else "unknown",
            version=version if isinstance(version, str) else None,
            database_updated=_parse_datetime(data.get("database_updated")),
            last_check=_parse_datetime(data.get("last_check")),
            checksum=checksum if isinstance(checksum, str) else None,
            size=size if isinstance(size, int) and not isinstance(size, bool) else None,
            last_error=last_error if isinstance(last_error, str) else None,
        )
        return self.status

    async def async_load_status(self) -> DatabaseStatus:
        return await self.hass.async_add_executor_job(self.load_status)

    def save_status(self) -> None:
        """Persist database metadata."""
        self.database_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(self.status)
        if self.status.database_updated is not None:
            data["database_updated"] = self.status.database_updated.isoformat()
        if self.status.last_check is not None:
            data["last_check"] = self.status.last_check.isoformat()
        self.metadata_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def async_save_status(self) -> None:
        await self.hass.async_add_executor_job(self.save_status)

    def calculate_checksum(self, path: str | Path | None = None) -> str:
        """Calculate the SHA-256 checksum of a database file."""
        target = Path(path) if path is not None else self.database_path
        digest = hashlib.sha256()
        with target.open("rb") as database_file:
            for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def validate_database(self, path: str | Path | None = None) -> bool:
        """Validate SQLite integrity and the schema required by Tsundoku."""
        database_path = Path(path) if path is not None else self.database_path
        if not database_path.is_file():
            return False
        connection = None
        try:
            connection = sqlite3.connect(database_path)
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                return False
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not set(_REQUIRED_COLUMNS).issubset(tables):
                return False
            for table, required in _REQUIRED_COLUMNS.items():
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if not required.issubset(columns):
                    return False
            return True
        except sqlite3.Error:
            return False
        finally:
            if connection is not None:
                connection.close()

    async def async_validate_database(self, path: str | Path | None = None) -> bool:
        return await self.hass.async_add_executor_job(self.validate_database, path)

    def refresh_local_status(self) -> DatabaseStatus:
        """Refresh status information from the local database."""
        if not self.database_path.is_file():
            self.status.status = "error"
            self.status.last_error = "Database file does not exist"
            self.status.checksum = None
            self.status.size = None
            return self.status
        if not self.validate_database():
            self.status.status = "error"
            self.status.last_error = "Database validation failed"
            self.status.checksum = None
            self.status.size = None
            return self.status
        self.status.status = "unknown"
        self.status.last_error = None
        self.status.checksum = self.calculate_checksum()
        self.status.size = self.database_path.stat().st_size
        return self.status

    async def async_refresh_local_status(self) -> DatabaseStatus:
        return await self.hass.async_add_executor_job(self.refresh_local_status)

    async def download_database(self, session: ClientSession, url: str) -> Path:
        """Download a database to a temporary file."""
        await self.hass.async_add_executor_job(
            lambda: self.database_dir.mkdir(parents=True, exist_ok=True)
        )
        timeout = ClientTimeout(total=300)
        temporary_path: Path | None = None
        temporary_file = None
        try:
            temporary_file = await self.hass.async_add_executor_job(
                lambda: NamedTemporaryFile(
                    dir=self.database_dir,
                    prefix=f"{DATABASE_FILENAME}.",
                    suffix=".tmp",
                    delete=False,
                )
            )
            temporary_path = Path(temporary_file.name)
            async with session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                async for chunk in response.content.iter_chunked(1024 * 1024):
                    await self.hass.async_add_executor_job(temporary_file.write, chunk)
            await self.hass.async_add_executor_job(temporary_file.close)
            return temporary_path
        except Exception:
            if temporary_file is not None and not temporary_file.closed:
                await self.hass.async_add_executor_job(temporary_file.close)
            if temporary_path is not None:
                await self.hass.async_add_executor_job(
                    lambda: temporary_path.unlink(missing_ok=True)
                )
            raise

    async def update(
        self,
        session: ClientSession,
        version: str,
        asset_url: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Download and install a new database atomically."""
        self.status.status = "updating"
        self.status.last_error = None
        try:
            if self.status.version == version and await self.async_validate_database():
                self.status.status = "up-to-date"
                self.status.last_check = now
                await self.async_save_status()
                return False

            temporary_path = await self.download_database(session, asset_url)
            try:
                if not await self.async_validate_database(temporary_path):
                    raise ValueError("Downloaded database validation failed")
                checksum = await self.hass.async_add_executor_job(
                    self.calculate_checksum, temporary_path
                )
                size = await self.hass.async_add_executor_job(
                    lambda: temporary_path.stat().st_size
                )
                await self.hass.async_add_executor_job(
                    temporary_path.replace, self.database_path
                )
            finally:
                await self.hass.async_add_executor_job(
                    lambda: temporary_path.unlink(missing_ok=True)
                )

            self.status.status = "up-to-date"
            self.status.version = version
            self.status.database_updated = now
            self.status.last_check = now
            self.status.checksum = checksum
            self.status.size = size
            self.status.last_error = None
            await self.async_save_status()
            return True
        except Exception as err:
            self.status.status = "error"
            self.status.last_check = now
            self.status.last_error = str(err)
            try:
                await self.async_save_status()
            except OSError:
                _LOGGER.exception("Could not save Tsundoku database status")
            raise


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
