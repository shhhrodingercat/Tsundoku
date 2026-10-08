# Tsundoku

Home Assistant custom integration for tracking manga volume releases.

Tsundoku is intended to track specific manga release lines and expose the next,
latest and published volume information to Home Assistant.

## Status

Early development — version 0.1.0.

## Planned data source

Volume metadata will be provided by the OpenTome / Mangarr metadata SQLite
dataset. The integration will download and maintain its own local copy of the
dataset rather than requiring an API key or external account.
