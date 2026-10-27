# Tsundoku

**Tsundoku** is a custom integration for [Home Assistant](https://www.home-assistant.io/) that tracks manga volume releases.

It shows the latest published volume and the next known release for each manga edition you follow, directly in Home Assistant.

## Features

- **Track manga editions:** each edition is a separate Home Assistant device, so Japanese and English releases of the same series can be tracked independently.
- **Search by title or alias:** find editions by title, local name or alias, optionally filtered by market/edition and language.
- **Database-backed filters:** market/edition and language dropdowns contain values found in the local metadata database.
- **Next release:** next known volume number and release date, preserving the precision of the source date. A volume stays the next one through its release day, so automations can act on it.
- **Latest release:** latest volume known to have been published.
- **Published volume count:** number of volumes known to have been published.
- **Optional calendar:** one **Tsundoku** calendar with the upcoming volumes of the editions you choose, as all-day events with the full volume data as JSON in the description. Off by default, turned on edition by edition. See [Calendar](#calendar).
- **Actions for automations:** get the volumes releasing today, in a range of days, next or in a month, with titles ready to use in a notification. See [Actions](#actions).
- **Manage tracked manga from the UI:** add or remove editions, and choose the ones in the calendar, through the integration options.
- **Automatic metadata updates:** a local copy of the metadata database is downloaded, validated and kept up to date in the background.
- **Diagnostics and manual updates:** database status sensors and an **Update database** button.
- **No API key required.**

## Data source and attribution

Tsundoku uses the SQLite metadata database published by [OpenTome / Mangarr](https://github.com/opentomedb/mangarr-metadata).

The bundled per-volume metadata artifact is described by the upstream project as a GCD-derived metadata artifact for Mangarr, licensed under **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)**.

Attribution and references:

- **Data source:** [Grand Comics Database](https://www.comics.org/)
- **Metadata project:** [OpenTome / Mangarr metadata](https://github.com/opentomedb/mangarr-metadata)
- **Metadata license:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

Metadata and release dates depend on the upstream dataset and may be incomplete, approximate or change over time. Coverage varies by market and edition; verify that the edition you want is available before relying on it.

### Database updates

- The database is downloaded during initial setup and stored locally in `<config>/tsundoku/`.
- Tsundoku checks for a newer release shortly after startup and then every 6 hours. You can also trigger an update check with the **Update database** button.
- A downloaded file replaces the current database only after validation, including a SQLite integrity check and schema validation. If a download fails or the file is invalid, the existing database is kept.
- Release dates are re-evaluated shortly after midnight so date-based sensors can update even when the database has not changed.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository, selecting **Integration** as the category.
3. Install Tsundoku and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **Tsundoku** and complete the setup.

### Manual installation

1. Copy the `custom_components/tsundoku` directory into the `custom_components` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**.
4. Search for **Tsundoku** and complete the setup.

## Setup and configuration

1. Add the integration and enter a title, or part of a title, in the search form.
2. Optionally select a **market / edition** and **language** from the dropdowns. These options are populated from values present in the local database. Market/edition values are not necessarily ISO country codes; upstream data may use values such as `EN`.
3. Select the edition or editions you want to track.
4. Choose which of them to show in the [calendar](#calendar). Leave everything unselected if you do not want it. Editions whose release dates only have a month or a year are listed as not available.

Only one Tsundoku instance can be configured. To change your list later, open the integration and choose **Configure**. You can search for and add editions, remove existing ones, or choose the editions in the calendar. When you add editions you are asked again which of the new ones go in the calendar. Removing an edition also removes its device and entities, and takes it out of the calendar.

## Entities

### Per tracked edition

Each edition is represented by a device named using its title and available edition metadata.

| Sensor | Description |
| --- | --- |
| Next volume | Number of the next volume with a known upcoming release. |
| Next release | Exact release date when the day is known. Its state is `unknown` when the release is known only to month precision. See [How release dates are interpreted](#how-release-dates-are-interpreted). |
| Latest volume | Number of the latest volume known to have been published. |
| Volumes | Number of volumes known to have been published. |

### Tsundoku device

| Entity | Description |
| --- | --- |
| Tsundoku | Optional [calendar](#calendar) with the upcoming volumes of the editions you chose. Only exists while at least one edition is in it. |

### Database diagnostics

| Entity | Description |
| --- | --- |
| Database status | Current state of the local database, such as up to date, updating or error. |
| Database version | Installed upstream release. |
| Database updated | When the database was last updated successfully. |
| Last check | When the last update check ran. |
| Database size | Size of the local database file. |
| Update database | Button that checks for and installs a newer database immediately. |

The database status sensor also exposes `checksum` and, after a failure, `last_error` as attributes.

## Calendar

The calendar is optional and **off by default**. When you add editions you are asked which of them to show in it, and you can change that at any time from **Configure → Calendar**. There is a single calendar, named **Tsundoku**, and every edition you choose is a source of events in it. It appears on the Tsundoku device as `calendar.tsundoku`, and only exists while at least one edition is in it.

What the calendar contains:

- **One all-day event for each volume with an exact release date.** The source provides dates, not times of day, so events are never timed.
- **Volumes dated to a month or a year only have no event**, because there is no day to put it on. An edition whose release dates are all like this cannot be in the calendar, and the setup and options say so. When the source adds the exact day of a volume, its event appears by itself. To follow those volumes use the [`get_month_releases`](#actions) action.
- **The past is never listed.** Events start from today: a volume released today is there, a volume released yesterday is not.
- **The title of an event is the manga name.** The volume is in the description.

### Event description

The description of an event is a JSON object, so an automation can read it without any text parsing. Its keys are the attributes of the **Next release** sensor, plus the volume and edition data. Values the source does not have are left out.

```json
{
  "series_name": "One Piece",
  "volume_number": 112,
  "title": "...",
  "release_date": "2026-11-04",
  "release_date_precision": "day",
  "release_date_raw": "2026-11-04",
  "release_date_type": "projected",
  "isbn13": "...",
  "country": "IT",
  "language": "it",
  "publisher": "Star Comics",
  "tome_id": "..."
}
```

`tome_id` identifies the edition, `volume_tome_id` the volume. `local_name` is the title in the local language, when the source has one. Each event also has a stable unique ID, `tsundoku-<tome id>-<volume number>`, that does not change when its date does.

### Example

Notify at 09:00 on the day a volume is released. Events are all-day, so the offset counts from midnight:

```yaml
alias: Volume out today
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.tsundoku
    offset: "9:00:00"
actions:
  - variables:
      release: "{{ trigger.calendar_event.description | from_json }}"
  - action: notify.notify
    data:
      title: "{{ release.series_name }}"
      message: "Volume {{ release.volume_number }} is out today."
```

## Actions

The actions return data for automations and scripts, to be used with `response_variable`. They work for every tracked edition, whether or not it is in the calendar, and they read the local database directly. All of them return the same response:

| Key | Description |
| --- | --- |
| `count` | Number of releases found. |
| `titles` | Manga titles, once each, in release order and ready to use in a message. The title is the manga name; the edition, for example `IT · Star Comics`, is added only when two different editions in the result share a name. |
| `releases` | The releases, in release order. Each one has the same keys as the [event description](#event-description). |

| Action | Fields | Description |
| --- | --- | --- |
| `tsundoku.get_releases` | `start_date` (default: today), `days` (default: 1) | Volumes released from `start_date` for `days` days. With no fields it returns what is released today. |
| `tsundoku.get_upcoming` | `limit` (default: 5) | The next `limit` volumes to be released, from today on. |
| `tsundoku.get_month_releases` | `month` (default: the current month, as `YYYY-MM`) | All the volumes of a month, including the ones dated to the month only. For those `release_date` is missing, `release_date_precision` is `month` and `release_date_display` has the localized month, for example `November 2026`. |

`get_releases` and `get_upcoming` only return volumes with an exact release date. `start_date` can be in the past. Volumes may be `projected` or `published`: `release_date_type` tells which.

### Examples

Tell me every morning what is released today:

```yaml
alias: Out today
triggers:
  - trigger: time
    at: "08:00:00"
actions:
  - action: tsundoku.get_releases
    response_variable: today
  - if:
      - condition: template
        value_template: "{{ today.count > 0 }}"
    then:
      - action: notify.notify
        data:
          title: Out today
          message: "{{ today.titles | join(', ') }}"
```

Tell me on the first day of the month what is expected, even without an exact day:

```yaml
alias: Expected this month
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: template
    value_template: "{{ now().day == 1 }}"
actions:
  - action: tsundoku.get_month_releases
    response_variable: month
  - if:
      - condition: template
        value_template: "{{ month.count > 0 }}"
    then:
      - action: notify.notify
        data:
          title: Expected this month
          message: "{{ month.titles | join(', ') }}"
```

## How release dates are interpreted

The source dataset does not always provide a full date. Tsundoku preserves that uncertainty instead of inventing a day.

- **Full dates (`YYYY-MM-DD`):** a volume is the next one through its release day, and counts as published from the day after. So on the day a volume is released the sensors still show it as the next volume and its date, and automations can act on it; the day after, it becomes the latest volume and the next one takes its place.
- **Month precision (`YYYY-MM`, for example `2026-11`):** a volume is the next one while its month is current or in the future, whatever the dataset says about it. It counts as published only after that month has ended and the dataset marks it as published, so it moves on when the following month starts.
- **Year precision (`YYYY`):** a volume counts as published only after the year has ended and the dataset marks it as published. Year-only dates are not reported as the next release.
- **No usable date:** the volume cannot be classified by date.

Sensors are re-evaluated shortly after midnight, so these changes happen at the start of the day after.

When the next release has only month precision, the **Next release** sensor has a state of `unknown`, because Home Assistant date sensors cannot represent a month without a day. Its attributes remain available and include the source date information and a localized display value, for example `November 2026`.

| Attribute | Description |
| --- | --- |
| `release_date_precision` | Precision supplied by the dataset, such as `day`, `month` or `year`. |
| `release_date_raw` | Original date representation, for example `2026-11`. |
| `release_date_type` | Date status supplied by the dataset, such as `projected` or `published`, when present. |
| `release_date_display` | Localized month and year when only month precision is known. |

Use these attributes in templates or automations when you need to distinguish an exact date from an approximate one. `unknown` means the exact date is not available; it does not necessarily mean that the integration has failed.

### Localization

The locale catalogs are stored in `custom_components/tsundoku/locales/`. They provide translated month names, language names and filter labels, with English as the fallback.

To contribute another locale, add a file such as `ja.json` following the structure of `en.json` and `it.json`. No Python changes should be needed for a locale that follows the existing catalog structure.

Home Assistant configuration-flow labels and entity names are translated separately in `custom_components/tsundoku/translations/`.

## Requirements

- Home Assistant 2026.8.0 or newer.
- An internet connection to download the metadata database and check for updates.

No external account or API key is required.

## Troubleshooting

- **Search finds nothing:** try a shorter title or alias and clear the market/edition and language filters. Not every edition is covered by the upstream dataset.
- **Database status shows an error:** inspect the `last_error` attribute. Press **Update database** to retry; the previous valid database remains in use if an update fails.
- **Setup fails on first install:** the initial database download requires internet access. Home Assistant will retry setup when possible.
- **Next release is `unknown`:** check `release_date_precision` and `release_date_raw`. If precision is `month`, the source does not provide a day, so `unknown` is expected rather than an integration error.
- **An edition cannot be put in the calendar:** all its release dates only have a month or a year. The calendar needs an exact day: use `tsundoku.get_month_releases` to follow it, and try again later from **Configure → Calendar**.
- **The calendar is empty or has fewer volumes than expected:** it lists the volumes with an exact release date from today on, for the editions in it. Volumes dated to a month only have no event until the source adds the day.

## Project status

Early development — version 0.2.0.

## Support the project

If you find Tsundoku useful and would like to contribute to its development and maintenance:

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/shhhrodingercat)

## Developer

Developed by **Matteo Miccichè**.

[LinkedIn](https://www.linkedin.com/in/miccichematteo/) · [Report a bug](https://github.com/shhhrodingercat/Tsundoku/issues)

## License

### Integration code

The Tsundoku integration code is released under the [MIT License](LICENSE).

### Metadata

The bundled GCD-derived per-volume metadata artifact for Mangarr is distributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), with attribution to the [Grand Comics Database](https://www.comics.org/) and reference to the [OpenTome / Mangarr metadata project](https://github.com/opentomedb/mangarr-metadata).

The integration code and the metadata are separate components and are subject to their respective license terms. Consult the upstream project for the complete metadata licensing and attribution information.
