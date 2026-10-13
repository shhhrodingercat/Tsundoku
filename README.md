# Tsundoku

**Tsundoku** is a custom integration for [Home Assistant](https://www.home-assistant.io/) that tracks manga volume releases.

It shows the latest published volume and the next known release for each manga edition you follow, directly in Home Assistant.

## Features

* **Track manga editions:** each edition is a separate Home Assistant device, so the Japanese and English releases of the same series are tracked independently.
* **Search by title or alias:** find editions by name, local name or alias, optionally filtered by market/edition and language. Filter choices are populated from values present in the local database.
* **Next release:** next known volume number and its release date.
* **Latest release:** latest volume that has already been published.
* **Published volume count:** number of volumes already published.
* **Manage tracked manga from the UI:** add or remove editions at any time from the integration options, without recreating the integration.
* **Automatic metadata updates:** a local copy of the metadata database is downloaded, validated and kept up to date in the background.
* **Diagnostics and manual update:** database status sensors and an **Update database** button.
* **No API key required.**

## Data source

Metadata comes from the SQLite database published by [OpenTome / Mangarr](https://github.com/opentomedb/mangarr-metadata). Please refer to the upstream repository for its license and attribution requirements.

How the database is handled:

* It is downloaded on first setup and stored locally in `<config>/tsundoku/`.
* Tsundoku checks for a newer release shortly after startup (in the background, so it never delays Home Assistant) and then every 6 hours. You can also trigger a check with the **Update database** button.
* A downloaded file replaces the current database only after it passes validation (SQLite integrity check and expected schema). If a download fails or the file is invalid, the current database is kept.
* Release dates are re-evaluated every day shortly after midnight, so the sensors change on the right day even when the database has not been updated.

Metadata and release dates depend on the upstream dataset and may be incomplete or change over time. Coverage varies by market: at the time of writing the dataset contains very few Italian editions, so check that the edition you want is searchable before relying on it.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository, selecting **Integration** as the category.
3. Install Tsundoku and restart Home Assistant.
4. Add Tsundoku from **Settings → Devices & services → Add integration**.

### Manual installation

1. Copy the `custom_components/tsundoku` directory into the `custom_components` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Add Tsundoku from **Settings → Devices & services → Add integration**.

## Setup

1. Add the integration and type a title (or part of it) in the search form. Optionally choose a **market / edition** and **language** from the dropdowns. Choices come from the values actually present in the database, so the market field is intentionally not described as an ISO country code: upstream data can contain values such as `EN`.
2. Select one or more editions to track.

Only one Tsundoku instance can be configured. To change your list later, open the integration and choose **Configure**: you can add new editions through a new search or remove existing ones. Removing an edition also removes its device and entities.

## Entities

### Per tracked edition

Each edition is a device named after the title, country, language and publisher, with these sensors:

| Sensor        | Description                                                                 |
| ------------- | --------------------------------------------------------------------------- |
| Next volume   | Number of the next volume with a known upcoming release                      |
| Next release  | Exact release date of that volume; unavailable when the source only provides a month |
| Latest volume | Number of the latest volume known to be published                            |
| Volumes       | Number of volumes known to be published                                      |

### Database (diagnostic)

| Entity          | Description                                                               |
| --------------- | ------------------------------------------------------------------------- |
| Database status | Current state of the local database (up to date, updating, error, ...)    |
| Database version| Installed upstream release                                                |
| Database updated| When the database was last updated                                        |
| Last check      | When the last update check ran                                            |
| Database size   | Size of the local database file                                           |
| Update database | Button that checks for and installs a newer database immediately          |

The status sensor also exposes `checksum` and, after a failure, `last_error` as attributes.

## How release dates are interpreted

Dates in the dataset do not always have day precision. Tsundoku handles them like this:

* **Full dates** are compared directly with today: a volume dated today or earlier is published, a later one is upcoming.
* **Month precision** (for example `2026-11`): the volume counts as published only once that month is over and the dataset marks it as published. It can be reported as *next* while its month is current or in the future, unless it is already marked as published. A volume that is marked as published and falls in the current month is therefore neither "latest" nor "next" until the month ends.
* **Year precision:** counts as published only once the year is over and the dataset marks it as published. It is never reported as the next release.
* **No date:** the volume cannot be classified and is ignored.

For a month-precision volume, **Next release** is `unavailable` rather than inventing a day. Its attributes keep the source precision and expose a localized month label (for example, `Novembre 2026` in Italian or `November 2026` in English). Month names and language labels are stored in JSON locale catalogs under `custom_components/tsundoku/locales/`, so contributors can add another locale without changing Python code. The sensor attributes are:

| Attribute                | Description                                              |
| ------------------------ | -------------------------------------------------------- |
| `release_date_precision` | `day`, `month` or `year`                                 |
| `release_date_raw`       | The date as stored in the dataset (e.g. `2026-11`)       |
| `release_date_type`      | Date status reported by the dataset (e.g. `projected`)   |
| `release_date_display`   | Localized month and year when only month precision is known |

Use these attributes in templates or automations when you need to tell an exact date from an approximate one.

## Requirements

* Home Assistant 2026.8.0 or newer
* An internet connection to download the metadata database and check for updates

No external account or API key is required.

## Troubleshooting

* **Search finds nothing:** try a shorter title or an alias, and clear the market/edition and language filters. Not every market is covered by the dataset.
* **Database status shows an error:** the `last_error` attribute explains why. Press **Update database** to retry; the previous valid database stays in use meanwhile.
* **Setup fails on first install:** the initial database download needs internet access. Home Assistant retries automatically.

## Project status

Early development, version 0.1.0.

## License

Tsundoku is released under the MIT License. See [LICENSE](LICENSE) for details.
