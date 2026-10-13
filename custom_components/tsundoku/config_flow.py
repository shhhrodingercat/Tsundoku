import logging
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, selector

from .const import DOMAIN
from .database import MangaDatabase
from .database_manager import DatabaseManager
from .models import ReleaseLine

_LOGGER = logging.getLogger(__name__)


class TsundokuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Tsundoku config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._search_results: list[ReleaseLine] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for managing tracked manga."""
        return TsundokuOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Search for manga release lines."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_configured")
        if user_input is None:
            return self._show_search_form()

        query = user_input.get("query", "").strip()
        if not query:
            return self._show_search_form(errors={"query": "empty_query"})

        manager = DatabaseManager(
            self.hass,
            self.hass.config.path("tsundoku"),
            aiohttp_client.async_get_clientsession(self.hass),
        )

        try:
            # Initialize only when the database is missing or invalid. Avoid
            # re-hashing the full database on every search submission.
            if not await manager.updater.async_validate_database():
                await manager.async_initialize()
            database = MangaDatabase(manager.database_path)
            self._search_results = await self.hass.async_add_executor_job(
                partial(
                    database.search_release_lines,
                    query,
                    country=user_input.get("country") or None,
                    language=user_input.get("language") or None,
                )
            )
        except Exception:
            _LOGGER.exception("Could not prepare Tsundoku database for search")
            return self._show_search_form(errors={"base": "cannot_connect"})

        if not self._search_results:
            return self._show_search_form(errors={"query": "no_results"})
        return await self.async_step_select()

    async def async_step_select(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Select the release lines to track."""
        if user_input is not None:
            tome_ids = user_input.get("tome_ids", [])
            if not tome_ids:
                return self.async_show_form(
                    step_id="select",
                    data_schema=self._selection_schema(),
                    errors={"base": "select_at_least_one"},
                )
            return self.async_create_entry(
                title=f"{len(tome_ids)} manga",
                data={"tome_ids": tome_ids},
            )

        return self.async_show_form(
            step_id="select",
            data_schema=self._selection_schema(),
        )

    def _selection_schema(self) -> vol.Schema:
        options = [
            {"value": line.tome_id, "label": self._format_release_line(line)}
            for line in self._search_results
        ]
        return vol.Schema(
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

    @staticmethod
    def _format_release_line(release_line: ReleaseLine) -> str:
        """Format a release line for display."""
        parts = [release_line.name]
        if release_line.country:
            parts.append(release_line.country)
        if release_line.language:
            parts.append(release_line.language)
        if release_line.publisher:
            parts.append(release_line.publisher)
        return " · ".join(parts)

    def _show_search_form(self, errors: dict[str, str] | None = None):
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


class TsundokuOptionsFlow(config_entries.OptionsFlow):
    """Manage release lines without creating duplicate integration entries."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._search_results: list[ReleaseLine] = []

    @property
    def _tracked_ids(self) -> list[str]:
        return list(
            self.config_entry.options.get(
                "tome_ids", self.config_entry.data.get("tome_ids", [])
            )
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Choose whether to add or remove tracked manga."""
        if user_input is not None:
            if user_input["action"] == "add":
                return await self.async_step_add_search()
            return await self.async_step_remove()

        options = [{"value": "add", "label": "Add manga"}]
        if self._tracked_ids:
            options.append({"value": "remove", "label": "Remove manga"})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="add"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_add_search(
        self, user_input: dict[str, Any] | None = None
    ):
        """Search for additional manga release lines."""
        if user_input is None:
            return self.async_show_form(
                step_id="add_search",
                data_schema=vol.Schema(
                    {
                        vol.Required("query"): str,
                        vol.Optional("country", default=""): str,
                        vol.Optional("language", default=""): str,
                    }
                ),
            )

        query = user_input.get("query", "").strip()
        if not query:
            return self.async_show_form(
                step_id="add_search",
                data_schema=vol.Schema(
                    {
                        vol.Required("query"): str,
                        vol.Optional("country", default=""): str,
                        vol.Optional("language", default=""): str,
                    }
                ),
                errors={"query": "empty_query"},
            )

        hass = self.hass
        manager = DatabaseManager(
            hass,
            hass.config.path("tsundoku"),
            aiohttp_client.async_get_clientsession(hass),
        )
        try:
            if not await manager.updater.async_validate_database():
                await manager.async_initialize()
            database = MangaDatabase(manager.database_path)
            self._search_results = await hass.async_add_executor_job(
                partial(
                    database.search_release_lines,
                    query,
                    country=user_input.get("country") or None,
                    language=user_input.get("language") or None,
                )
            )
        except Exception:
            _LOGGER.exception("Could not search the Tsundoku database")
            return self.async_show_form(
                step_id="add_search",
                data_schema=vol.Schema(
                    {
                        vol.Required("query"): str,
                        vol.Optional("country", default=""): str,
                        vol.Optional("language", default=""): str,
                    }
                ),
                errors={"base": "cannot_connect"},
            )

        if not self._search_results:
            return self.async_show_form(
                step_id="add_search",
                data_schema=vol.Schema(
                    {
                        vol.Required("query"): str,
                        vol.Optional("country", default=""): str,
                        vol.Optional("language", default=""): str,
                    }
                ),
                errors={"query": "no_results"},
            )
        return await self.async_step_add_select()

    async def async_step_add_select(
        self, user_input: dict[str, Any] | None = None
    ):
        """Select and add release lines."""
        if user_input is not None:
            selected = user_input.get("tome_ids", [])
            if not selected:
                return self.async_show_form(
                    step_id="add_select",
                    data_schema=self._selection_schema(),
                    errors={"base": "select_at_least_one"},
                )
            updated = list(dict.fromkeys(self._tracked_ids + selected))
            return self.async_create_entry(title="", data={"tome_ids": updated})
        return self.async_show_form(
            step_id="add_select", data_schema=self._selection_schema()
        )

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ):
        """Remove selected release lines from tracking."""
        tracked_ids = self._tracked_ids
        if not tracked_ids:
            return self.async_create_entry(title="", data={"tome_ids": []})

        if user_input is not None:
            selected = set(user_input.get("tome_ids", []))
            if not selected:
                return self.async_show_form(
                    step_id="remove",
                    data_schema=await self._remove_schema(),
                    errors={"base": "select_at_least_one"},
                )
            updated = [tome_id for tome_id in tracked_ids if tome_id not in selected]
            return self.async_create_entry(title="", data={"tome_ids": updated})

        return self.async_show_form(
            step_id="remove", data_schema=await self._remove_schema()
        )

    def _selection_schema(self) -> vol.Schema:
        options = [
            {
                "value": line.tome_id,
                "label": TsundokuConfigFlow._format_release_line(line),
            }
            for line in self._search_results
        ]
        return vol.Schema(
            {
                vol.Required("tome_ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

    async def _remove_schema(self) -> vol.Schema:
        """Build a selection form with labels for the currently tracked lines."""
        hass = self.hass
        database = MangaDatabase(
            hass.config.path("tsundoku", "manga-metadata.sqlite")
        )
        try:
            labels = await hass.async_add_executor_job(
                _format_tracked_lines, database, self._tracked_ids
            )
        except Exception:
            _LOGGER.exception("Could not resolve tracked manga names")
            labels = [
                {"value": tome_id, "label": tome_id}
                for tome_id in self._tracked_ids
            ]
        return vol.Schema(
            {
                vol.Required("tome_ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=labels,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )


def _format_tracked_lines(
    database: MangaDatabase, tome_ids: list[str]
) -> list[dict[str, str]]:
    """Resolve stored IDs to readable labels for the removal form."""
    options = []
    for tome_id in tome_ids:
        line = database.get_release_line(tome_id)
        label = (
            TsundokuConfigFlow._format_release_line(line)
            if line is not None
            else tome_id
        )
        options.append({"value": tome_id, "label": label})
    return options
