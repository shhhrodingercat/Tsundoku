# Tsundoku

**Tsundoku** is a custom integration for [Home Assistant](https://www.home-assistant.io/) that tracks manga volume releases.

It shows the latest published volume and the next known release for each manga edition you follow, directly in Home Assistant.

## Features

- **Track manga editions:** each edition is a separate Home Assistant device, so Japanese and English releases of the same series can be tracked independently.
- **Search by title or alias:** find editions by title, local name or alias, optionally filtered by market/edition and language.
- **Database-backed filters:** market/edition and language dropdowns contain values found in the local metadata database, rather than requiring users to know dataset-specific codes.
- **Next release:** next known volume number and release date, with the precision of the source date preserved.
- **Latest release:** latest volume known to have been published.
- **Published volume count:** number of volumes known to have been published.
- **Manage tracked manga from the UI:** add or remove editions from the integration options without recreating the integration.
- **Automatic metadata updates:** a local copy of the metadata database is downloaded, validated and kept up to date in the background.
- **Diagnostics and manual update:** database status sensors and an **Update database** button.
- **No API key required.**

## Data source

Metadata comes from the SQLite database published by [OpenTome / Mangarr](https://github.com/opentomedb/mangarr-metadata). Please refer to the upstream repository for its license and attribution requirements.

How the database is handled:

- It is downloaded on first setup and stored locally in `<config>/tsundoku/`.
- Tsundoku checks for a newer release shortly after startup in the background, then every 6 hours. You can also trigger a check with the **Update database** button.
- A downloaded file replaces the current database only after it passes validation, including a SQLite integrity check and schema validation. If a download fails or the file is invalid, the current database is kept.
- Release dates are re-evaluated shortly after midnight so date-based sensors update even when the database has not changed.

Metadata and release dates depend on the upstream dataset and may be incomplete or change over time. Coverage varies by market and edition; verify that the edition you want is available before relying on it.

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

## Setup and configuration

1. Add the integration and enter a title (or part of it) in the search form.
2. Optionally select a **market / edition** and **language** from the dropdowns. Their choices are populated from values actually present in the local database. The market/edition field is deliberately not described as an ISO country code because upstream data may use non-standard values such as `EN`.
3. Select the edition or editions you want to track.

Only one Tsundoku instance can be configured. To change your list later, open the integration and choose **Configure**. You can search for and add editions or remove existing ones. Removing an edition also removes its device and entities.

## Entities

### Per tracked edition

Each edition is a device named using the title and available edition metadata. It provides these sensors:

| Sensor | Description |
| --- | --- |
| Next volume | Number of the next volume with a known upcoming release. |
| Next release | Exact release date when the day is known; its state is `unknown` when the next release is known only to month precision. See [How release dates are interpreted](#how-release-dates-are-interpreted). |
| Latest volume | Number of the latest volume known to have been published. |
| Volumes | Number of volumes known to have been published. |

### Database diagnostics

| Entity | Description |
| --- | --- |
| Database status | Current state of the local database (up to date, updating, error, and so on). |
| Database version | Installed upstream release. |
| Database updated | When the database was last updated successfully. |
| Last check | When the last update check ran. |
| Database size | Size of the local database file. |
| Update database | Button that checks for and installs a newer database immediately. |

The database status sensor also exposes `checksum` and, after a failure, `last_error` as attributes.

## How release dates are interpreted

The source dataset does not always provide a full date. Tsundoku preserves that uncertainty instead of inventing a day.

- **Full dates (`YYYY-MM-DD`):** compared directly with the current date. A volume dated today or earlier can be treated as published; a later date is upcoming.
- **Month precision (`YYYY-MM`, for example `2026-11`):** the volume counts as published only after that month has ended and the dataset marks it as published. It can be reported as the next volume while its month is current or in the future, unless it is already marked as published. A volume marked as published in the current month is therefore neither the latest nor the next volume until the month ends.
- **Year precision (`YYYY`):** counts as published only after the year has ended and the dataset marks it as published. Year-only dates are not reported as the next release.
- **No usable date:** the volume cannot be classified by date.

When the next release has only month precision, the **Next release** sensor has a state of `unknown` because Home Assistant date sensors cannot represent a month without a day. Its attributes remain available and include the source date information and a localized display value, for example `Novembre 2026` or `November 2026`.

| Attribute | Description |
| --- | --- |
| `release_date_precision` | Precision supplied by the dataset, such as `day`, `month` or `year`. |
| `release_date_raw` | Original date representation, for example `2026-11`. |
| `release_date_type` | Date status supplied by the dataset, such as `projected` or `published`, when present. |
| `release_date_display` | Localized month and year when only month precision is known. |

Use these attributes in templates or automations when you need to distinguish an exact date from an approximate one. Remember that `unknown` means the exact date is not available; it does not necessarily mean that the integration has failed.

### Localization

The locale catalogs are stored in `custom_components/tsundoku/locales/`. They provide translated month names, language names and filter labels, with English as the fallback. To contribute another locale, add a file such as `ja.json` following the structure of `en.json` and `it.json`. No Python changes should be needed for a locale that follows the existing catalog structure.

The Home Assistant configuration-flow labels and entity names are translated separately in `custom_components/tsundoku/translations/`.

## Requirements

- Home Assistant 2026.8.0 or newer.
- An internet connection to download the metadata database and check for updates.

No external account or API key is required.

## Troubleshooting

- **Search finds nothing:** try a shorter title or alias, and clear the market/edition and language filters. Not every edition is covered by the upstream dataset.
- **Database status shows an error:** inspect the `last_error` attribute. Press **Update database** to retry; the previous valid database remains in use while an update fails.
- **Setup fails on first install:** the initial database download needs internet access. Home Assistant will retry setup when possible.
- **Next release is `unknown`:** check `release_date_precision` and `release_date_raw`. If precision is `month`, the source does not provide a day, so `unknown` is expected rather than an integration error.

## Project status

Early development, version 0.1.0.

## ☕ Supporta il progetto

Se ti è utile e vuoi contribuire ai costi di sviluppo e manutenzione:

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/shhhrodingercat)

---

## 👤 Sviluppatore

Sviluppato da **Matteo Miccichè**  
[LinkedIn](https://www.linkedin.com/in/miccichematteo/) · [Segnala un bug](https://github.com/shhhrodingercat/Tsundoku/issues)


## License

Tsundoku is released under the MIT License. See [LICENSE](LICENSE) for details.
