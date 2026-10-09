import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from aiohttp import ClientSession, ClientTimeout

DATABASE_FILENAME = "manga-metadata.sqlite"
METADATA_FILENAME = "metadata.json"


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

    def __init__(self, database_dir: str | Path) -> None:
        self.database_dir = Path(database_dir)
        self.database_path = self.database_dir / DATABASE_FILENAME
        self.metadata_path = self.database_dir / METADATA_FILENAME
        self.status = DatabaseStatus(status="unknown")

    def load_status(self) -> DatabaseStatus:
        """Load persisted database metadata."""
        if not self.metadata_path.exists():
            return self.status

        try:
            data = json.loads(
                self.metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return self.status

        self.status = DatabaseStatus(
            status=data.get("status", "unknown"),
            version=data.get("version"),
            database_updated=_parse_datetime(
                data.get("database_updated")
            ),
            last_check=_parse_datetime(
                data.get("last_check")
            ),
            checksum=data.get("checksum"),
            size=data.get("size"),
            last_error=data.get("last_error"),
        )

        return self.status

    def save_status(self) -> None:
        """Persist database metadata."""
        self.database_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = asdict(self.status)

        if self.status.database_updated is not None:
            data["database_updated"] = (
                self.status.database_updated.isoformat()
            )

        if self.status.last_check is not None:
            data["last_check"] = (
                self.status.last_check.isoformat()
            )

        self.metadata_path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

    def calculate_checksum(self) -> str:
        """Calculate the SHA-256 checksum of the local database."""
        digest = hashlib.sha256()

        with self.database_path.open("rb") as database_file:
            for chunk in iter(
                lambda: database_file.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    def validate_database(
        self,
        path: str | Path | None = None,
    ) -> bool:
        """Validate that a database file is usable SQLite."""
        database_path = (
            Path(path)
            if path is not None
            else self.database_path
        )

        if not database_path.is_file():
            return False

        try:
            with sqlite3.connect(database_path) as connection:
                result = connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()

                return result == ("ok",)
        except sqlite3.Error:
            return False

    def refresh_local_status(self) -> DatabaseStatus:
        """Refresh status information from the local database."""
        if not self.database_path.is_file():
            self.status.status = "error"
            self.status.last_error = (
                "Database file does not exist"
            )
            self.status.checksum = None
            self.status.size = None
            return self.status

        if not self.validate_database():
            self.status.status = "error"
            self.status.last_error = (
                "Database validation failed"
            )
            self.status.checksum = None
            self.status.size = None
            return self.status

        self.status.status = "unknown"
        self.status.last_error = None
        self.status.checksum = self.calculate_checksum()
        self.status.size = self.database_path.stat().st_size

        return self.status

    async def download_database(
        self,
        session: ClientSession,
        url: str,
    ) -> Path:
        """Download a database to a temporary file."""
        self.database_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        timeout = ClientTimeout(total=300)
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                dir=self.database_dir,
                prefix=f"{DATABASE_FILENAME}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                async with session.get(
                    url,
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()

                    async for chunk in response.content.iter_chunked(
                        1024 * 1024
                    ):
                        temporary_file.write(chunk)

            return temporary_path

        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    async def update(
        self,
        session: ClientSession,
        version: str,
        asset_url: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Download and install a new database."""
        self.status.status = "updating"
        self.status.last_error = None

        try:
            if self.status.version == version:
                self.status.status = "up-to-date"
                self.status.last_check = now
                self.save_status()
                return False

            temporary_path = await self.download_database(
                session,
                asset_url,
            )

            try:
                if not self.validate_database(temporary_path):
                    raise ValueError(
                        "Downloaded database validation failed"
                    )

                checksum = _calculate_checksum(temporary_path)
                size = temporary_path.stat().st_size

                temporary_path.replace(self.database_path)

            finally:
                temporary_path.unlink(missing_ok=True)

            self.status.status = "up-to-date"
            self.status.version = version
            self.status.database_updated = now
            self.status.last_check = now
            self.status.checksum = checksum
            self.status.size = size
            self.status.last_error = None
            self.save_status()

            return True

        except Exception as err:
            self.status.status = "error"
            self.status.last_check = now
            self.status.last_error = str(err)
            self.save_status()
            raise


def _calculate_checksum(path: Path) -> str:
    """Calculate the SHA-256 checksum of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    """Parse an ISO 8601 datetime."""
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
