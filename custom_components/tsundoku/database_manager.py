
import logging
from datetime import datetime
from pathlib import Path

from aiohttp import ClientSession

from .database_updater import DatabaseStatus, DatabaseUpdater
from .fetcher import DatabaseFetcher

_LOGGER = logging.getLogger(__name__)


class DatabaseManager:
    """Coordinate remote database checks and local updates."""

    def __init__(
        self,
        database_dir: str | Path,
        session: ClientSession,
    ) -> None:
        self.session = session
        self.updater = DatabaseUpdater(database_dir)
        self.fetcher = DatabaseFetcher(session)

    @property
    def status(self) -> DatabaseStatus:
        """Return the current database status."""
        return self.updater.status

    @property
    def database_path(self) -> Path:
        """Return the path of the local database."""
        return self.updater.database_path

    async def async_initialize(self) -> DatabaseStatus:
        """Load local state and download the database if missing."""
        self.updater.load_status()

        if not self.database_path.is_file():
            remote = await self.fetcher.get_latest_database()

            await self.updater.update(
                self.session,
                remote.version,
                remote.asset_url,
                now=datetime.now().astimezone(),
            )

            return self.status

        self.updater.refresh_local_status()

        return self.status

    async def async_check_for_update(self) -> bool:
        """Check for a newer database and install it if available."""
        now = datetime.now().astimezone()
        self.status.status = "checking"
        self.status.last_check = now
        self.status.last_error = None

        try:
            remote = await self.fetcher.get_latest_database()

            if self.status.version == remote.version:
                self.status.status = "up-to-date"
                self.status.last_error = None
                self.updater.save_status()
                return False

            return await self.updater.update(
                self.session,
                remote.version,
                remote.asset_url,
                now=now,
            )

        except Exception as err:
            self.status.status = "error"
            self.status.last_error = str(err)

            try:
                self.updater.save_status()
            except OSError:
                _LOGGER.exception(
                    "Could not save Tsundoku database status"
                )

            raise
