from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import DOMAIN
from .database import MangaDatabase
from .models import ReleaseLine


class TsundokuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Tsundoku config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._search_results: list[ReleaseLine] = []

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Search for manga release lines."""
        if user_input is not None:
            query = user_input["query"].strip()

            if not query:
                return self._show_search_form(
                    errors={"query": "empty_query"},
                )

            database = self._get_database(self.hass)

            self._search_results = await self.hass.async_add_executor_job(
                partial(
                    database.search_release_lines,
                    query,
                    country=user_input.get("country") or None,
                    language=user_input.get("language") or None,
                )
            )

            if not self._search_results:
                return self._show_search_form(
                    errors={"query": "no_results"},
                )

            return await self.async_step_select()

        return self._show_search_form()

    async def async_step_select(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Select the release lines to track."""
        if user_input is not None:
            tome_ids = user_input["tome_ids"]

            return self.async_create_entry(
                title=f"{len(tome_ids)} manga",
                data={
                    "tome_ids": tome_ids,
                },
            )

        options = [
            selector.SelectOptionDict(
                value=release_line.tome_id,
                label=self._format_release_line(release_line),
            )
            for release_line in self._search_results
        ]

        schema = vol.Schema(
            {
                vol.Required("tome_ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="select",
            data_schema=schema,
        )

    @staticmethod
    def _format_release_line(
        release_line: ReleaseLine,
    ) -> str:
        """Format a release line for display."""
        parts = [release_line.name]

        if release_line.country:
            parts.append(release_line.country)

        if release_line.language:
            parts.append(release_line.language)

        if release_line.publisher:
            parts.append(release_line.publisher)

        return " · ".join(parts)

    @staticmethod
    @callback
    def _get_database(
        hass: HomeAssistant,
    ) -> MangaDatabase:
        """Return the Tsundoku database."""
        return MangaDatabase(
            hass.config.path(
                "tsundoku",
                "manga-metadata.sqlite",
            )
        )

    def _show_search_form(
        self,
        errors: dict[str, str] | None = None,
    ):
        """Show the manga search form."""
        schema = vol.Schema(
            {
                vol.Required("query"): str,
                vol.Optional("country", default=""): str,
                vol.Optional("language", default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors or {},
        )