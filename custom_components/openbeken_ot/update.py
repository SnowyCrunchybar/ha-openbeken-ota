"""Update platform for OpenBeken devices discovered via HA Device Registry."""
import asyncio
import logging
from urllib.parse import quote, urlparse, urlunparse

import aiohttp

from homeassistant.components import mqtt
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHIPSET_ASSET_PATTERNS, DOMAIN
from .coordinator import OpenBekenReleaseCoordinator

_LOGGER = logging.getLogger(__name__)


def _extract_openbeken_ip(device: dr.DeviceEntry) -> str | None:
    """Return IP address if the device is an MQTT-based OpenBeken device."""
    is_mqtt = any(identifier[0] == "mqtt" for identifier in device.identifiers)
    if not is_mqtt:
        return None

    if not device.configuration_url:
        return None

    parsed = urlparse(device.configuration_url)
    if not parsed.hostname:
        return None

    manufacturer = (device.manufacturer or "").lower()
    sw_version = (device.sw_version or "").lower()
    model = (device.model or "").upper()
    identifiers_str = str(device.identifiers).lower()

    is_openbeken = (
        "openbeken" in manufacturer
        or "beken" in manufacturer
        or "openbk" in sw_version
        or "openbeken" in sw_version
        or "openbeken" in identifiers_str
        or "obk" in identifiers_str
        or any(chip in model for chip in CHIPSET_ASSET_PATTERNS)
    )

    if not is_openbeken:
        return None

    return parsed.hostname


def _extract_mqtt_topic_name(device: dr.DeviceEntry) -> str | None:
    """Extract case-sensitive OpenBeken Client Topic (Short name) for MQTT commands."""
    # OpenBeken's MQTT discovery sets device.name to its exact case-sensitive Short name / Client Topic
    if device.name:
        return device.name.strip()

    for domain_key, ident_value in device.identifiers:
        if domain_key == "mqtt" and ident_value:
            return str(ident_value).strip()
    return None


def _detect_chipset_from_device(device: dr.DeviceEntry) -> str | None:
    """Extract chipset name from DeviceEntry model or sw_version."""
    combined = f"{device.model or ''} {device.sw_version or ''}".upper()
    for chip in CHIPSET_ASSET_PATTERNS:
        if chip in combined:
            return chip
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenBeken update entities and listen for new or updated devices dynamically."""
    coordinator: OpenBekenReleaseCoordinator = hass.data[DOMAIN][entry.entry_id]
    dev_reg = dr.async_get(hass)

    initial_entities: list[OpenBekenUpdateEntity] = []
    for device in dev_reg.devices:
        if device.id in coordinator.entities:
            continue
        ip_address = _extract_openbeken_ip(device)
        if ip_address:
            entity = OpenBekenUpdateEntity(coordinator, device, ip_address)
            coordinator.register_entity(device.id, entity)
            initial_entities.append(entity)

    _LOGGER.info(
        "Discovered %d existing MQTT OpenBeken device(s) from Device Registry",
        len(initial_entities),
    )

    if initial_entities:
        async_add_entities(initial_entities, update_before_add=True)

    @callback
    def _handle_device_registry_updated(
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """Handle device creation or IP address update in the device registry."""
        action = event.data["action"]
        if action not in ("create", "update"):
            return

        device_id = event.data["device_id"]
        device = dev_reg.async_get(device_id)
        if not device:
            return

        new_ip = _extract_openbeken_ip(device)
        if not new_ip:
            return

        existing_entity = coordinator.entities.get(device_id)
        if isinstance(existing_entity, OpenBekenUpdateEntity):
            existing_entity.update_device_entry(device)
            if existing_entity.ip_address != new_ip:
                _LOGGER.info(
                    "OpenBeken device %s IP changed: %s -> %s",
                    existing_entity.device_name,
                    existing_entity.ip_address,
                    new_ip,
                )
                existing_entity.set_ip_address(new_ip)
                hass.async_create_task(existing_entity.async_refresh_and_notify())
            return

        _LOGGER.info(
            "Discovered new OpenBeken device %s (%s), adding OTA update entity",
            device.name,
            new_ip,
        )
        entity = OpenBekenUpdateEntity(coordinator, device, new_ip)
        coordinator.register_entity(device_id, entity)
        async_add_entities([entity], update_before_add=True)

    entry.async_on_unload(
        hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, _handle_device_registry_updated
        )
    )


class OpenBekenUpdateEntity(
    CoordinatorEntity[OpenBekenReleaseCoordinator], UpdateEntity
):
    """Representation of an OpenBeken OTA update entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.BACKUP
        | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_has_entity_name = True
    _attr_name = "Firmware"

    def __init__(
        self,
        coordinator: OpenBekenReleaseCoordinator,
        device: dr.DeviceEntry,
        ip_address: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self._device = device
        self._ip_address = ip_address
        self._mqtt_topic_name: str | None = _extract_mqtt_topic_name(device)
        self._chipset: str | None = _detect_chipset_from_device(device)
        self._installed_version: str | None = (
            str(device.sw_version).lstrip("v") if device.sw_version else None
        )

        device_label = device.name_by_user or device.name or f"OpenBeken ({ip_address})"
        self._attr_unique_id = f"{device.id}_ota_update"
        self._attr_device_info = {
            "identifiers": device.identifiers,
            "name": device_label,
        }

    @property
    def device_name(self) -> str:
        """Return user-friendly device name."""
        return self._device.name_by_user or self._device.name or self._ip_address

    @property
    def ip_address(self) -> str:
        """Return current device IP address."""
        return self._ip_address

    @property
    def mqtt_topic_name(self) -> str | None:
        """Return the case-sensitive OpenBeken MQTT device topic name."""
        return self._mqtt_topic_name

    def set_ip_address(self, ip_address: str) -> None:
        """Update the target IP address dynamically."""
        self._ip_address = ip_address

    def update_device_entry(self, device: dr.DeviceEntry) -> None:
        """Keep the cached DeviceEntry reference fresh and sync fallback metadata."""
        self._device = device
        if not self._mqtt_topic_name:
            self._mqtt_topic_name = _extract_mqtt_topic_name(device)
        if not self._chipset:
            self._chipset = _detect_chipset_from_device(device)
        if not self._installed_version and device.sw_version:
            self._installed_version = str(device.sw_version).lstrip("v")

    async def async_refresh_and_notify(self) -> None:
        """Poll the updated IP address and notify summary sensors/buttons."""
        await self.async_update()
        self.async_write_ha_state()
        self.coordinator.async_update_listeners()

    async def async_update(self) -> None:
        """Fetch current firmware version and chipset directly from the device API."""
        if not self._chipset:
            self._chipset = _detect_chipset_from_device(self._device)
        if not self._installed_version and self._device.sw_version:
            self._installed_version = str(self._device.sw_version).lstrip("v")

        session = async_get_clientsession(self.hass)
        url = f"http://{self._ip_address}/api/info"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    info = await resp.json(content_type=None)
                    if "version" in info:
                        self._installed_version = str(info["version"]).lstrip("v")
                    if "chipset" in info:
                        self._chipset = str(info["chipset"]).upper()
        except Exception as err:
            _LOGGER.warning(
                "Could not poll %s (%s) via HTTP /api/info: %s (using registry fallback: version=%s, chipset=%s)",
                self.device_name,
                self._ip_address,
                err,
                self._installed_version,
                self._chipset,
            )

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed version."""
        return self._installed_version

    @property
    def latest_version(self) -> str | None:
        """Return the latest version available for this chipset."""
        if not self.coordinator.data:
            return None
        if self._chipset and self._chipset in self.coordinator.data.get("assets", {}):
            return self.coordinator.data.get("latest_version")
        return self._installed_version

    @property
    def release_url(self) -> str | None:
        """Return the URL to the release page."""
        return (
            self.coordinator.data.get("release_url") if self.coordinator.data else None
        )

    def release_notes(self) -> str | None:
        """Return the release notes."""
        return (
            self.coordinator.data.get("release_notes")
            if self.coordinator.data
            else None
        )

    def _match_subnet_ota_url(self, local_ota_url: str) -> str:
        """Ensure HA host IP in the OTA URL matches the device's 10.0.1.x subnet if applicable."""
        if self._ip_address.startswith("10.0.1."):
            parsed = urlparse(local_ota_url)
            port = parsed.port or 8123
            new_netloc = f"10.0.1.112:{port}"
            return urlunparse(parsed._replace(scheme="http", netloc=new_netloc))
        return local_ota_url

    async def async_install(
        self, version: str | None = None, backup: bool = False, **kwargs
    ) -> None:
        """Optionally back up config, cache .rbl binary locally, and trigger OTA via HTTP (with MQTT fallback)."""
        if not self._chipset:
            raise HomeAssistantError(
                f"Cannot update {self.device_name}: unknown chipset."
            )

        if backup:
            await self.coordinator.async_backup_device(
                self.device_name, self._ip_address
            )

        raw_ota_url = await self.coordinator.async_get_local_ota_url(self._chipset)
        local_ota_url = self._match_subnet_ota_url(raw_ota_url)

        session = async_get_clientsession(self.hass)
        encoded_url = quote(local_ota_url, safe="")
        ota_cmd_url = f"http://{self._ip_address}/cm?cmnd=ota_http%20{encoded_url}"

        _LOGGER.info(
            "Triggering local OTA update for %s (%s) via HTTP -> %s",
            self.device_name,
            self._ip_address,
            local_ota_url,
        )

        http_ok = False
        try:
            async with session.get(
                ota_cmd_url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                body = await resp.text()
                _LOGGER.info(
                    "HTTP ota_http response from %s (%s): HTTP %s - %s",
                    self.device_name,
                    self._ip_address,
                    resp.status,
                    body.strip(),
                )
                if resp.status == 200:
                    http_ok = True
        except Exception as err:
            _LOGGER.warning(
                "HTTP ota_http failed for %s (%s): %s; falling back to MQTT",
                self.device_name,
                self._ip_address,
                err,
            )

        if not http_ok:
            if not self._mqtt_topic_name:
                raise HomeAssistantError(
                    f"HTTP OTA failed for {self.device_name} and no MQTT topic is available"
                )
            cmnd_topic = f"cmnd/{self._mqtt_topic_name}/ota_http"
            _LOGGER.info(
                "Fallback: Triggering local OTA update for %s via MQTT topic '%s' -> %s",
                self.device_name,
                cmnd_topic,
                local_ota_url,
            )
            await mqtt.async_publish(
                self.hass, cmnd_topic, local_ota_url, qos=1, retain=False
            )

        # Wait for device to download .rbl, flash, and start rebooting
        await asyncio.sleep(20)

        # Poll the device up to 6 times (every 5s) until it comes back online with the new version
        target_version = self.latest_version
        for attempt in range(6):
            await self.async_update()
            if target_version and self._installed_version == target_version:
                _LOGGER.info(
                    "%s successfully updated to version %s",
                    self.device_name,
                    self._installed_version,
                )
                break
            _LOGGER.debug(
                "Waiting for %s to finish rebooting (attempt %d/6, current version: %s)...",
                self.device_name,
                attempt + 1,
                self._installed_version,
            )
            await asyncio.sleep(5)

        self.async_write_ha_state()
        self.coordinator.async_update_listeners()