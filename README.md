# Tsundoku

**Tsundoku** is a custom integration for [Home Assistant](https://www.home-assistant.io/) that tracks manga volume releases.

It helps you keep track of the latest published volume and upcoming releases for the manga editions you follow, directly from Home Assistant.

## Features

* **Track manga editions:** each tracked release line is represented as a separate Home Assistant device.
* **Search manga:** find editions using their titles and aliases.
* **Upcoming releases:** see the next known volume number and release date.
* **Latest releases:** see the latest volume whose release date has passed.
* **Published volume count:** track the number of volumes with a release date up to the current date.
* **Automatic metadata updates:** download and maintain a local copy of the manga metadata database.
* **No API key required:** metadata is sourced from the OpenTome / Mangarr dataset.

Different editions of the same manga, such as Japanese and English releases, can be tracked independently.

## Data source

Tsundoku uses the SQLite metadata database published by [OpenTome / Mangarr](https://github.com/opentomedb/mangarr-metadata).

The database is downloaded locally and updated when a newer release is available. The integration checks for updates at startup and periodically thereafter.

The local database is validated before a downloaded version replaces the existing one. This allows Tsundoku to retain its current database if a download fails or the new file is invalid.

Manga metadata and release dates depend on the upstream dataset and may be incomplete or change over time.

## Installation

### HACS

Tsundoku is intended to be distributed as a custom HACS integration.

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository, selecting **Integration** as the category.
3. Install Tsundoku.
4. Restart Home Assistant.
5. Add Tsundoku through **Settings → Devices & services → Add integration**.

### Manual installation

1. Copy the `custom_components/tsundoku` directory into your Home Assistant configuration's `custom_components` directory.
2. Restart Home Assistant.
3. Add Tsundoku through **Settings → Devices & services → Add integration**.

## Sensors

Each tracked manga edition exposes the following sensors:

| Sensor        | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| Next volume   | Number of the next volume with a known future release date         |
| Next release  | Release date of the next known upcoming volume                     |
| Latest volume | Number of the latest volume with a release date on or before today |
| Volumes       | Number of volumes with a known release date on or before today     |

If a release date is unavailable, the corresponding volume cannot be reliably classified as upcoming or already released.

## Requirements

* Home Assistant
* An internet connection for downloading the metadata database and checking for updates

No external account or API key is required.

## Project status

Early development — version 0.1.0.

## License

Tsundoku is released under the MIT License. See [LICENSE](LICENSE) for details.

