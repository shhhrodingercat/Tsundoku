import logging
from functools import partial
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import (
    aiohttp_client,
    device_registry,
    entity_registry,
    selector,
)

from .const import CONF_CALENDAR_IDS, CONF_TOME_IDS, DOMAIN, NAME
from .database import MangaDatabase
from .database_manager import DatabaseManager
from .database_updater import DATABASE_FILENAME
from .localization import load_locale_catalog
from .models import ReleaseLine

_LOGGER = logging.getLogger(__name__)

# Shown in a form when there is no release line to list.
_NONE = "—"


def _search_schema(
    countries: list[str], languages: list[str], catalog: dict[str, Any]
) -> vol.Schema:
    """Build a search form with choices backed by the local database."""
    labels = catalog.get("labels", {})
    language_names = catalog.get("languages", {})
    country_options = [
        {
            "value": "",
            "label": labels.get("all_markets", "All markets / editions"),
        }
    ]
    country_options.extend({"value": code, "label": code} for code in countries)
    language_options = [
        {"value": "", "label": labels.get("all_languages", "All languages")}
    ]
    language_options.extend(
        {
            "value": code,
            "label": f"{code} — {language_names.get(code.lower(), code)}",
        }
        for code in languages
    )
    return vol.Schema(
        {
            vol.Required("query"): str,
            vol.Optional("country", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=country_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("language", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=language_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _calendar_schema(
    options: list[dict[str, str]], suggested: list[str] | None = None
) -> vol.Schema:
    """Build the form that picks the release lines in the calendar."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_CALENDAR_IDS,
                default=list,
                description={"suggested_value": suggested or []},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _chosen_calendar_ids(user_input: dict[str, Any], allowed: list[str]) -> list[str]:
    """Return the release lines picked in a calendar form, in ``allowed`` order."""
    picked = set(user_input.get(CONF_CALENDAR_IDS, []))
    return [tome_id for tome_id in allowed if tome_id in picked]


def _unavailable_text(unavailable: list[str]) -> str:
    return ", ".join(unavailable) or _NONE


def _calendar_choices(
    database: MangaDatabase, tome_ids: list[str], enabled: set[str]
) -> tuple[list[dict[str, str]], list[str]]:
    """Split release lines into those that can be in the calendar and those not.

    A release line can be in the calendar if at least one of its volumes has an
    exact release date. The ones already in the calendar are always listed, so
    they can be taken out. Returns the options and the labels of the others.
    """
    lines = {}
    for tome_id in tome_ids:
        line = database.get_release_line(tome_id)
        if line is not None:
            lines[tome_id] = line
    exact = database.get_series_ids_with_exact_dates(
        [line.id for line in lines.values()]
    )
    options: list[dict[str, str]] = []
    unavailable: list[str] = []
    for tome_id in tome_ids:
        line = lines.get(tome_id)
        label = TsundokuConfigFlow._format_release_line(line) if line else tome_id
        if tome_id in enabled or (line is not None and line.id in exact):
            options.append({"value": tome_id, "label": label})
        else:
            unavailable.append(label)
    return options, unavailable


async def _async_calendar_form(
    flow: config_entries.ConfigFlow | config_entries.OptionsFlow,
    step_id: str,
    database_path: Path,
    tome_ids: list[str],
    enabled: list[str],
) -> ConfigFlowResult:
    """Show the calendar form, or its "not available" variant.

    ``<step_id>_unavailable`` is shown when no release line can be in the
    calendar, because their release dates only have a month or a year.
    """
    try:
        options, unavailable = await flow.hass.async_add_executor_job(
            _calendar_choices, MangaDatabase(database_path), tome_ids, set(enabled)
        )
    except Exception:
        _LOGGER.exception("Could not check which Tsundoku release lines have dates")
        return flow.async_show_form(
            step_id=step_id,
            data_schema=_calendar_schema([]),
            errors={"base": "cannot_connect"},
            description_placeholders={"unavailable": _NONE},
        )
    placeholders = {"unavailable": _unavailable_text(unavailable)}
    if not options:
        return flow.async_show_form(
            step_id=f"{step_id}_unavailable", description_placeholders=placeholders
        )
    suggested = [option["value"] for option in options if option["value"] in enabled]
    return flow.async_show_form(
        step_id=step_id,
        data_schema=_calendar_schema(options, suggested),
        description_placeholders=placeholders,
    )


class TsundokuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Tsundoku config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._search_results: list[ReleaseLine] = []
        self._countries: list[str] = []
        self._languages: list[str] = []
        self._catalog: dict[str, Any] = {}
        self._selected: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for managing tracked manga."""
        return TsundokuOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Search for manga release lines."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_configured")
        manager = DatabaseManager(
            self.hass,
            self.hass.config.path("tsundoku"),
            aiohttp_client.async_get_clientsession(self.hass),
        )

        if user_input is None:
            self._catalog = await self.hass.async_add_executor_job(
                load_locale_catalog, self.hass.config.language
            )
            try:
                if not await manager.updater.async_validate_database():
                    await manager.async_initialize()
                database = MangaDatabase(manager.database_path)
                (
                    self._countries,
                    self._languages,
                ) = await self.hass.async_add_executor_job(
                    database.get_search_filter_options
                )
            except Exception:
                _LOGGER.exception("Could not load Tsundoku search filters")
                return self._show_search_form(errors={"base": "cannot_connect"})
            return self._show_search_form()

        query = user_input.get("query", "").strip()
        if not query:
            return self._show_search_form(errors={"query": "empty_query"})

        try:
            # Recheck only when the database is missing or invalid.
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
            tome_ids = user_input.get(CONF_TOME_IDS, [])
            if not tome_ids:
                return self.async_show_form(
                    step_id="select",
                    data_schema=self._selection_schema(),
                    errors={"base": "select_at_least_one"},
                )
            self._selected = tome_ids
            return await self.async_step_calendars()

        return self.async_show_form(
            step_id="select",
            data_schema=self._selection_schema(),
        )

    async def async_step_calendars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which selected release lines go in the calendar, then finish."""
        if user_input is not None:
            return self._create_tsundoku_entry(
                _chosen_calendar_ids(user_input, self._selected)
            )
        database_path = Path(self.hass.config.path("tsundoku")) / DATABASE_FILENAME
        return await _async_calendar_form(
            self, "calendars", database_path, self._selected, []
        )

    async def async_step_calendars_unavailable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tell that none of the selected release lines can be in the calendar."""
        return self._create_tsundoku_entry([])

    def _create_tsundoku_entry(self, calendar_ids: list[str]) -> ConfigFlowResult:
        return self.async_create_entry(
            title=NAME,
            data={CONF_TOME_IDS: self._selected},
            options={CONF_CALENDAR_IDS: calendar_ids},
        )

    def _selection_schema(self) -> vol.Schema:
        options = [
            {"value": line.tome_id, "label": self._format_release_line(line)}
            for line in self._search_results
        ]
        return vol.Schema(
            {
                vol.Required(CONF_TOME_IDS): selector.SelectSelector(
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
        """Show the manga search form with database-backed filter choices."""
        return self.async_show_form(
            step_id="user",
            data_schema=_search_schema(self._countries, self._languages, self._catalog),
            errors=errors or {},
        )


class TsundokuOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage release lines and the calendar without duplicate integration entries.

    Every step stores the full options dict: an options flow replaces it.
    """

    def __init__(self) -> None:
        self._search_results: list[ReleaseLine] = []
        self._countries: list[str] = []
        self._languages: list[str] = []
        self._catalog: dict[str, Any] = {}
        self._added: list[str] = []

    @property
    def _database_path(self) -> Path:
        """Return the active database path, even if setup has failed."""
        runtime_data = getattr(self.config_entry, "runtime_data", None)
        manager = getattr(runtime_data, "database_manager", None)
        if manager is not None:
            return manager.database_path
        return Path(self.hass.config.path("tsundoku")) / DATABASE_FILENAME

    @property
    def _tracked_ids(self) -> list[str]:
        return list(
            self.config_entry.options.get(
                CONF_TOME_IDS, self.config_entry.data.get(CONF_TOME_IDS, [])
            )
        )

    @property
    def _calendar_ids(self) -> list[str]:
        return list(self.config_entry.options.get(CONF_CALENDAR_IDS, []))

    def _options(self) -> dict[str, Any]:
        """Return the current options, with the tracked and calendar lists."""
        return {
            **self.config_entry.options,
            CONF_TOME_IDS: self._tracked_ids,
            CONF_CALENDAR_IDS: self._calendar_ids,
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to change."""
        menu = ["add_search"]
        if self._tracked_ids:
            menu.extend(["remove", "calendars"])
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_search(
        self, user_input: dict[str, Any] | None = None
    ):
        """Search for additional manga release lines."""
        if user_input is None:
            self._catalog = await self.hass.async_add_executor_job(
                load_locale_catalog, self.hass.config.language
            )
            try:
                database_path = self._database_path
                if not database_path.is_file():
                    raise FileNotFoundError("Tsundoku metadata database is unavailable")
                database = MangaDatabase(database_path)
                (
                    self._countries,
                    self._languages,
                ) = await self.hass.async_add_executor_job(
                    database.get_search_filter_options
                )
            except Exception:
                _LOGGER.exception("Could not load Tsundoku search filters")
                return self._show_add_search_form(errors={"base": "cannot_connect"})
            return self._show_add_search_form()

        query = user_input.get("query", "").strip()
        if not query:
            return self._show_add_search_form(errors={"query": "empty_query"})

        try:
            database_path = self._database_path
            if not database_path.is_file():
                raise FileNotFoundError("Tsundoku metadata database is unavailable")
            database = MangaDatabase(database_path)
            self._search_results = await self.hass.async_add_executor_job(
                partial(
                    database.search_release_lines,
                    query,
                    country=user_input.get("country") or None,
                    language=user_input.get("language") or None,
                )
            )
        except Exception:
            _LOGGER.exception("Could not search the Tsundoku database")
            return self._show_add_search_form(errors={"base": "cannot_connect"})

        if not self._search_results:
            return self._show_add_search_form(errors={"query": "no_results"})
        return await self.async_step_add_select()

    def _show_add_search_form(
        self, errors: dict[str, str] | None = None
    ):
        """Show the options-flow search form with translated filter choices."""
        return self.async_show_form(
            step_id="add_search",
            data_schema=_search_schema(self._countries, self._languages, self._catalog),
            errors=errors or {},
        )

    async def async_step_add_select(
        self, user_input: dict[str, Any] | None = None
    ):
        """Select the release lines to add."""
        if user_input is not None:
            selected = user_input.get(CONF_TOME_IDS, [])
            if not selected:
                return self.async_show_form(
                    step_id="add_select",
                    data_schema=self._selection_schema(),
                    errors={"base": "select_at_least_one"},
                )
            self._added = selected
            return await self.async_step_add_calendars()
        return self.async_show_form(
            step_id="add_select", data_schema=self._selection_schema()
        )

    async def async_step_add_calendars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which added release lines go in the calendar, then save both lists."""
        if user_input is not None:
            return self._save_added(_chosen_calendar_ids(user_input, self._added))
        return await _async_calendar_form(
            self, "add_calendars", self._database_path, self._added, []
        )

    async def async_step_add_calendars_unavailable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tell that none of the added release lines can be in the calendar."""
        return self._save_added([])

    def _save_added(self, calendar_ids: list[str]) -> ConfigFlowResult:
        updated = list(dict.fromkeys(self._tracked_ids + self._added))
        calendars = list(dict.fromkeys(self._calendar_ids + calendar_ids))
        return self.async_create_entry(
            title="",
            data={
                **self._options(),
                CONF_TOME_IDS: updated,
                CONF_CALENDAR_IDS: calendars,
            },
        )

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ):
        """Remove selected release lines from tracking."""
        tracked_ids = self._tracked_ids
        if not tracked_ids:
            return self.async_create_entry(
                title="", data={**self._options(), CONF_TOME_IDS: []}
            )

        if user_input is not None:
            selected = set(user_input.get(CONF_TOME_IDS, []))
            if not selected:
                return self.async_show_form(
                    step_id="remove",
                    data_schema=await self._remove_schema(),
                    errors={"base": "select_at_least_one"},
                )
            updated = [tome_id for tome_id in tracked_ids if tome_id not in selected]
            calendars = [
                tome_id for tome_id in self._calendar_ids if tome_id in updated
            ]
            _remove_manga_registry_entries(
                self.hass, self.config_entry, tracked_ids=set(selected)
            )
            return self.async_create_entry(
                title="",
                data={
                    **self._options(),
                    CONF_TOME_IDS: updated,
                    CONF_CALENDAR_IDS: calendars,
                },
            )

        return self.async_show_form(
            step_id="remove", data_schema=await self._remove_schema()
        )

    async def async_step_calendars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which tracked release lines are in the calendar."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self._options(),
                    CONF_CALENDAR_IDS: _chosen_calendar_ids(
                        user_input, self._tracked_ids
                    ),
                },
            )
        return await _async_calendar_form(
            self,
            "calendars",
            self._database_path,
            self._tracked_ids,
            self._calendar_ids,
        )

    async def async_step_calendars_unavailable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tell that none of the tracked release lines can be in the calendar."""
        return self.async_create_entry(title="", data=self._options())

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
                vol.Required(CONF_TOME_IDS): selector.SelectSelector(
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
        try:
            database_path = self._database_path
            if not database_path.is_file():
                raise FileNotFoundError("Tsundoku metadata database is unavailable")
            database = MangaDatabase(database_path)
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
                vol.Required(CONF_TOME_IDS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=labels,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )


def _remove_manga_registry_entries(
    hass, config_entry: config_entries.ConfigEntry, tracked_ids: set[str]
) -> None:
    """Remove registry entities and devices for explicitly untracked manga."""
    if not tracked_ids:
        return

    entities = entity_registry.async_get(hass)
    devices = device_registry.async_get(hass)
    for entity in list(entities.entities.values()):
        if entity.config_entry_id == config_entry.entry_id and any(
            entity.unique_id.startswith(f"{tome_id}_")
            for tome_id in tracked_ids
        ):
            entities.async_remove(entity.entity_id)

    for device in list(devices.devices.values()):
        if any((DOMAIN, tome_id) in device.identifiers for tome_id in tracked_ids):
            # Only remove a device after its Tsundoku entities have been removed.
            if not any(
                entity.device_id == device.id
                for entity in entities.entities.values()
            ):
                devices.async_remove_device(device.id)


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
