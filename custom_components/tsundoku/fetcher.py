from dataclasses import dataclass
from datetime import datetime

from aiohttp import ClientSession, ClientTimeout

GITHUB_API_URL = (
    "https://api.github.com/repos/"
    "opentomedb/mangarr-metadata/releases/latest"
)
DATABASE_ASSET_NAME = "manga-metadata.sqlite"
USER_AGENT = "Home Assistant Tsundoku"


@dataclass(frozen=True)
class RemoteDatabase:
    """Information about the latest remote database."""

    version: str
    asset_url: str
    published_at: datetime
    commit: str | None = None


class DatabaseFetcher:
    """Fetch database information from OpenTomeDB."""

    def __init__(
        self,
        session: ClientSession,
        api_url: str = GITHUB_API_URL,
    ) -> None:
        self.session = session
        self.api_url = api_url

    async def get_latest_database(self) -> RemoteDatabase:
        """Return information about the latest database release."""
        timeout = ClientTimeout(total=30)

        async with self.session.get(
            self.api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        version = data.get("tag_name")
        published_at = data.get("published_at")
        commit = data.get("target_commitish")

        if not version:
            raise ValueError(
                "GitHub release has no tag_name"
            )

        if not published_at:
            raise ValueError(
                "GitHub release has no published_at"
            )

        assets = data.get("assets", [])

        asset_url = next(
            (
                asset["browser_download_url"]
                for asset in assets
                if asset.get("name") == DATABASE_ASSET_NAME
            ),
            None,
        )

        if not asset_url:
            raise ValueError(
                f"GitHub release has no "
                f"{DATABASE_ASSET_NAME} asset"
            )

        return RemoteDatabase(
            version=version,
            asset_url=asset_url,
            published_at=datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            ),
            commit=commit,
        )
