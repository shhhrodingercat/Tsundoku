DOMAIN = "tsundoku"
NAME = "Tsundoku"

# Entry data holds the tracked release lines chosen at setup; the options, which
# take precedence once they exist, hold everything the user changes later.
CONF_TOME_IDS = "tome_ids"
CONF_CALENDAR_IDS = "calendar_ids"

# Key of the optional per-release-line calendar entity (unique ID:
# "<tome id>_calendar").
CALENDAR_KEY = "calendar"

# Actions.
SERVICE_GET_RELEASES = "get_releases"
SERVICE_GET_UPCOMING = "get_upcoming"
SERVICE_GET_MONTH_RELEASES = "get_month_releases"
ATTR_START_DATE = "start_date"
ATTR_DAYS = "days"
ATTR_LIMIT = "limit"
ATTR_MONTH = "month"
DEFAULT_RELEASE_DAYS = 1
MAX_RELEASE_DAYS = 366
DEFAULT_UPCOMING_LIMIT = 5
MAX_UPCOMING_LIMIT = 50
