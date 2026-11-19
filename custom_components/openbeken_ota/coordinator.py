"""DataUpdateCoordinator for fetching OpenBeken releases, caching binaries, and backing up configs."""
import asyncio
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import re
from urllib.parse import urlparse

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKUP_DIR,
    CHIPSET_ASSET_PATTERNS,
    DOMAIN,
    GITHUB_API_URL,
    SCAN_INTERVAL_HOURS,
    WWW_SUBDIR,
)

_LOGGER = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Sanitize device name for safe directory creation."""
    cleaned = re.sub(r"[^\w\-. ]", "_", name).strip()
    return cleaned or "unknown_device"


class OpenBekenReleaseCoordinator(DataUpdateCoordinator):
    """Class to manage fetching OpenBeken release data, tracking devices, and backups."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=SCAN_INTERVAL_HOURS),
        )
        self._download_locks: dict[str, asyncio.Lock] = {}
        self.entities: dict[str, object] = {}

    def register_entity(self, device_id: str, entity: object) -> None:
        """Register an OpenBekenUpdateEntity for summary tracking."""
        self.entities[device_id] = entity

    def get_device_summary(self) -> dict:
        """Return lists of up-to-date and outdated devices."""
        up_to_date = []
        outdated = []

        for entity in self.entities.values():
            name = entity.device_name
            installed = entity.installed_version
            latest = entity.latest_version

            if not installed or not latest:
                continue

            if installed != latest:
                outdated.append(
                    {
                        "name": name,
                        "installed": installed,
                        "latest": latest,
                        "ip": entity.ip_address,
                    }
                )
            else:
                up_to_date.append(
                    {
                        "name": name,
                        "version": installed,
                        "ip": entity.ip_address,
                    }
                )

        return {
            "up_to_date": up_to_date,
            "outdated": outdated,
        }

    async def async_backup_device(self, device_name: str, ip_address: str) -> Path:
        """Download config.json and autoexec.bat (if present) from an OpenBeken device."""
        session = async_get_clientsession(self.hass)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_name = _sanitize_filename(device_name)
        target_dir = Path(self.hass.config.path(BACKUP_DIR, safe_name, timestamp))

        # 1. Fetch config.json via /api/obkconfig
        config_url = f"http://{ip_address}/api/obkconfig"
        try:
            async with session.get(
                config_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    raise HomeAssistantError(
                        f"HTTP {resp.status} while fetching config from {ip_address}"
                    )
                raw_config = await resp.text()
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to backup config for {device_name} ({ip_address}): {err}"
            ) from err

        # Pretty-print JSON if valid, otherwise save raw text
        try:
            parsed_json = json.loads(raw_config)
            config_text = json.dumps(parsed_json, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            config_text = raw_config

        # 2. Fetch autoexec.bat via /api/lfs/autoexec.bat (optional file)
        autoexec_text: str | None = None
        autoexec_url = f"http://{ip_address}/api/lfs/autoexec.bat"
        try:
            async with session.get(
                autoexec_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    autoexec_text = await resp.text()
        except Exception as err:
            _LOGGER.debug(
                "Could not fetch autoexec.bat for %s (%s): %s",
                device_name,
                ip_address,
                err,
            )

        def _write_backup_files() -> None:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "config.json").write_text(config_text, encoding="utf-8")
            if autoexec_text is not None:
                (target_dir / "autoexec.bat").write_text(
                    autoexec_text, encoding="utf-8"
                )

        await self.hass.async_add_executor_job(_write_backup_files)
        _LOGGER.info(
            "Backed up %s (%s) to %s (autoexec.bat included: %s)",
            device_name,
            ip_address,
            target_dir,
            autoexec_text is not None,
        )
        return target_dir

    async def async_backup_all_devices(self) -> None:
        """Backup config.json and autoexec.bat for all registered OpenBeken devices."""
        _LOGGER.info(
            "Starting full backup for %d OpenBeken devices", len(self.entities)
        )
        for entity in self.entities.values():
            try:
                await self.async_backup_device(entity.device_name, entity.ip_address)
            except Exception as err:
                _LOGGER.error(
                    "Backup failed for %s (%s): %s",
                    entity.device_name,
                    entity.ip_address,
                    err,
                )

    async def _async_update_data(self) -> dict:
        """Fetch latest release info and map .rbl OTA download URLs per chipset."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                GITHUB_API_URL, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"GitHub API returned status {resp.status}")
                data = await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with GitHub API: {err}") from err

        tag_name = data.get("tag_name", "").lstrip("v")
        release_notes = data.get("body", "")
        release_url = data.get("html_url", "")
        assets = data.get("assets", [])

        asset_info = {}
        for chipset, (prefix, suffix) in CHIPSET_ASSET_PATTERNS.items():
            for asset in assets:
                name = asset.get("name", "")
                if (
                    name.startswith(prefix)
                    and name.endswith(suffix)
                    and "_UG_" not in name
                ):
                    asset_info[chipset] = {
                        "name": name,
                        "url": asset.get("browser_download_url"),
                    }
                    break

        return {
            "latest_version": tag_name,
            "release_notes": release_notes,
            "release_url": release_url,
            "assets": asset_info,
        }

    def _get_local_http_base_url(self) -> str:
        """Determine Home Assistant's local plain HTTP base URL for OTA devices."""
        try:
            internal_url = get_url(self.hass, allow_external=False, prefer_external=False)
            parsed = urlparse(internal_url)
            host = parsed.hostname
            port = parsed.port or self.hass.http.server_port or 8123
            return f"http://{host}:{port}"
        except NoURLAvailableError:
            host = self.hass.config.api.local_ip
            port = self.hass.http.server_port or 8123
            return f"http://{host}:{port}"

    async def async_get_local_ota_url(self, chipset: str) -> str:
        """Download firmware binary to config/www if needed and return local HTTP URL."""
        assets = self.data.get("assets", {}) if self.data else {}
        asset = assets.get(chipset)
        if not asset:
            raise HomeAssistantError(f"No release binary found for chipset {chipset}.")

        filename = asset["name"]
        github_url = asset["url"]

        lock = self._download_locks.setdefault(chipset, asyncio.Lock())
        async with lock:
            www_dir = Path(self.hass.config.path("www", WWW_SUBDIR))
            target_file = www_dir / filename

            if not await self.hass.async_add_executor_job(target_file.exists):
                _LOGGER.info("Downloading %s from GitHub to local cache...", filename)
                session = async_get_clientsession(self.hass)
                try:
                    async with session.get(
                        github_url, timeout=aiohttp.ClientTimeout(total=60)
                    ) as resp:
                        if resp.status != 200:
                            raise HomeAssistantError(
                                f"Failed to download binary from GitHub (HTTP {resp.status})"
                            )
                        binary_data = await resp.read()
                except Exception as err:
                    raise HomeAssistantError(
                        f"Error downloading {filename} from GitHub: {err}"
                    ) from err

                def _write_and_cleanup() -> None:
                    www_dir.mkdir(parents=True, exist_ok=True)
                    prefix, suffix = CHIPSET_ASSET_PATTERNS[chipset]
                    for old_file in www_dir.glob(f"{prefix}*"):
                        if old_file.name != filename:
                            old_file.unlink(missing_ok=True)
                    target_file.write_bytes(binary_data)

                await self.hass.async_add_executor_job(_write_and_cleanup)
                _LOGGER.info("Cached %s locally (%d bytes)", filename, len(binary_data))

        base_url = self._get_local_http_base_url()
        return f"{base_url}/local/{WWW_SUBDIR}/{filename}"