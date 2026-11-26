"""Constants for the OpenBeken OTA Updater integration."""

DOMAIN = "openbeken_ota"
GITHUB_API_URL = (
    "https://api.github.com/repos/openshwprojects/OpenBK7231T_App/releases/latest"
)
SCAN_INTERVAL_HOURS = 6
WWW_SUBDIR = "openbeken_ota"
BACKUP_DIR = "openbeken_backups"

CONF_INCLUDE_BATTERY_DEVICES = "include_battery_devices"
DEFAULT_INCLUDE_BATTERY_DEVICES = False

CONF_RETRY_FAILED_UPDATES = "retry_failed_updates"
DEFAULT_RETRY_FAILED_UPDATES = True

CONF_RETRY_DELAY_MINUTES = "retry_delay_minutes"
DEFAULT_RETRY_DELAY_MINUTES = 3

MAX_OTA_RETRIES = 3

# Maps normalized chipset names to (filename_prefix, filename_suffix) for OTA .rbl files
CHIPSET_ASSET_PATTERNS: dict[str, tuple[str, str]] = {
    "BK7231T": ("OpenBK7231T_", ".rbl"),
    "BK7231N": ("OpenBK7231N_", ".rbl"),
    "BK7238": ("OpenBK7238_", ".rbl"),
    "BL602": ("OpenBL602_", ".rbl"),
    "W800": ("OpenW800_", ".rbl"),
    "W600": ("OpenW600_", ".rbl"),
}
