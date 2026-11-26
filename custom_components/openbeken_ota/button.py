"""Button platform for manual OpenBeken OTA updates, backups, and restarts."""
import logging

import aiohttp

from homeassistant.components import mqtt
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenBekenReleaseCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenBeken OTA, backup, and restart buttons."""
    coordinator: OpenBekenReleaseCoordinator = hass.data[DOMAIN][entry.entry_id]
    dev_reg = dr.async_get(hass)
    known_button_ids: set[str] = set()

    # Global action buttons
    entities: list[ButtonEntity] = [
        OpenBekenCheckUpdatesButton(coordinator, entry.entry_id),
        OpenBekenBackupAllButton(coordinator, entry.entry_id),
        OpenBekenUpdateAllButton(coordinator, entry.entry_id, with_backup=False),
        OpenBekenUpdateAllButton(coordinator, entry.entry_id, with_backup=True),
    ]

    # Per-device buttons for existing OpenBeken devices
    for device_id, update_entity in coordinator.entities.items():
        if device_id in known_button_ids:
            continue
        device = dev_reg.async_get(device_id)
        if device:
            known_button_ids.add(device_id)
            entities.extend(
                [
                    OpenBekenDeviceCheckButton(coordinator, device, update_entity),
                    OpenBekenDeviceUpdateButton(
                        coordinator, device, update_entity, with_backup=False
                    ),
                    OpenBekenDeviceUpdateButton(
                        coordinator, device, update_entity, with_backup=True
                    ),
                    OpenBekenDeviceRestartButton(coordinator, device, update_entity),
                ]
            )

    async_add_entities(entities)

    # Listen for newly discovered devices to add their buttons dynamically
    @callback
    def _handle_new_device(
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        if event.data["action"] not in ("create", "update"):
            return
        device_id = event.data["device_id"]
        if device_id in known_button_ids or device_id not in coordinator.entities:
            return

        device = dev_reg.async_get(device_id)
        if not device:
            return

        known_button_ids.add(device_id)
        update_entity = coordinator.entities[device_id]
        async_add_entities(
            [
                OpenBekenDeviceCheckButton(coordinator, device, update_entity),
                OpenBekenDeviceUpdateButton(
                    coordinator, device, update_entity, with_backup=False
                ),
                OpenBekenDeviceUpdateButton(
                    coordinator, device, update_entity, with_backup=True
                ),
                OpenBekenDeviceRestartButton(coordinator, device, update_entity),
            ]
        )

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _handle_new_device)
    )


class OpenBekenDeviceCheckButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to check for updates on a single OpenBeken device."""

    _attr_has_entity_name = True
    _attr_name = "Tarkista päivitykset"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: OpenBekenReleaseCoordinator,
        device: dr.DeviceEntry,
        update_entity: object,
    ) -> None:
        """Initialize device check button."""
        super().__init__(coordinator)
        self._update_entity = update_entity
        self._attr_unique_id = f"{device.id}_check_button"
        device_label = device.name_by_user or device.name or update_entity.ip_address
        self._attr_device_info = {
            "identifiers": device.identifiers,
            "name": device_label,
        }

    async def async_press(self) -> None:
        """Fetch latest release info from GitHub and poll this device."""
        await self.coordinator.async_request_refresh()
        await self._update_entity.async_update()
        self._update_entity.async_write_ha_state()
        self.coordinator.async_update_listeners()


class OpenBekenDeviceUpdateButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to trigger manual OTA update (with or without backup) for a single device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OpenBekenReleaseCoordinator,
        device: dr.DeviceEntry,
        update_entity: object,
        with_backup: bool,
    ) -> None:
        """Initialize device update button."""
        super().__init__(coordinator)
        self._update_entity = update_entity
        self._with_backup = with_backup

        if with_backup:
            self._attr_name = "Varmuuskopioi ja päivitä"
            self._attr_icon = "mdi:content-save-move"
            self._attr_unique_id = f"{device.id}_backup_and_ota_button"
        else:
            self._attr_name = "Päivitä firmware"
            self._attr_icon = "mdi:cellphone-arrow-down"
            self._attr_unique_id = f"{device.id}_ota_button"

        device_label = device.name_by_user or device.name or update_entity.ip_address
        self._attr_device_info = {
            "identifiers": device.identifiers,
            "name": device_label,
        }

    @property
    def available(self) -> bool:
        """Button is available when an update is actually pending."""
        installed = self._update_entity.installed_version
        latest = self._update_entity.latest_version
        return bool(installed and latest and installed != latest)

    async def async_press(self) -> None:
        """Trigger OTA update (and optional backup) when pressed."""
        await self._update_entity.async_install(backup=self._with_backup)
        self.coordinator.async_update_listeners()


class OpenBekenDeviceRestartButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to reboot a single OpenBeken device via HTTP (with MQTT fallback)."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_has_entity_name = True
    _attr_name = "Käynnistä uudelleen"

    def __init__(
        self,
        coordinator: OpenBekenReleaseCoordinator,
        device: dr.DeviceEntry,
        update_entity: object,
    ) -> None:
        """Initialize device restart button."""
        super().__init__(coordinator)
        self._update_entity = update_entity
        self._attr_unique_id = f"{device.id}_restart_button"
        device_label = device.name_by_user or device.name or update_entity.ip_address
        self._attr_device_info = {
            "identifiers": device.identifiers,
            "name": device_label,
        }

    async def async_press(self) -> None:
        """Send Restart command via HTTP, falling back to case-sensitive MQTT topic."""
        ip_address = self._update_entity.ip_address
        restart_url = f"http://{ip_address}/cm?cmnd=Restart"
        session = async_get_clientsession(self.hass)

        _LOGGER.info(
            "Sending Restart command to OpenBeken device %s (%s) via HTTP",
            self._update_entity.device_name,
            ip_address,
        )

        try:
            async with session.get(
                restart_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return
        except Exception as err:
            _LOGGER.warning(
                "HTTP Restart failed for %s (%s): %s; falling back to MQTT",
                self._update_entity.device_name,
                ip_address,
                err,
            )

        mqtt_topic = getattr(self._update_entity, "mqtt_topic_name", None)
        if mqtt_topic:
            cmnd_topic = f"cmnd/{mqtt_topic}/Restart"
            _LOGGER.info(
                "Fallback: Sending Restart command to %s via MQTT topic '%s'",
                self._update_entity.device_name,
                cmnd_topic,
            )
            await mqtt.async_publish(self.hass, cmnd_topic, "1", qos=1, retain=False)
            return

        raise HomeAssistantError(
            f"Failed to restart {self._update_entity.device_name} ({ip_address}) via HTTP or MQTT"
        )


class OpenBekenCheckUpdatesButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to force check GitHub and poll all OpenBeken devices."""

    _attr_name = "OpenBeken Tarkista päivitykset"
    _attr_icon = "mdi:refresh"

    def __init__(
        self, coordinator: OpenBekenReleaseCoordinator, entry_id: str
    ) -> None:
        """Initialize check button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_check_updates_button"

    async def async_press(self) -> None:
        """Refresh GitHub release info and poll all devices."""
        await self.coordinator.async_request_refresh()
        for entity in self.coordinator.entities.values():
            await entity.async_update()
            entity.async_write_ha_state()
        self.coordinator.async_update_listeners()


class OpenBekenBackupAllButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to back up config.json and autoexec.bat for all OpenBeken devices."""

    _attr_name = "OpenBeken Varmuuskopioi kaikki"
    _attr_icon = "mdi:content-save-all"

    def __init__(
        self, coordinator: OpenBekenReleaseCoordinator, entry_id: str
    ) -> None:
        """Initialize backup-all button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_backup_all_button"

    async def async_press(self) -> None:
        """Trigger backup for all discovered OpenBeken devices."""
        await self.coordinator.async_backup_all_devices()


class OpenBekenUpdateAllButton(
    CoordinatorEntity[OpenBekenReleaseCoordinator], ButtonEntity
):
    """Button to update all outdated OpenBeken devices."""

    def __init__(
        self,
        coordinator: OpenBekenReleaseCoordinator,
        entry_id: str,
        with_backup: bool,
    ) -> None:
        """Initialize update-all button."""
        super().__init__(coordinator)
        self._with_backup = with_backup

        if with_backup:
            self._attr_name = "OpenBeken Varmuuskopioi ja päivitä kaikki"
            self._attr_icon = "mdi:content-save-cog"
            self._attr_unique_id = f"{entry_id}_backup_and_update_all_button"
        else:
            self._attr_name = "OpenBeken Päivitä kaikki vanhentuneet"
            self._attr_icon = "mdi:update"
            self._attr_unique_id = f"{entry_id}_update_all_button"

    @property
    def available(self) -> bool:
        """Enable button only if at least one device needs an update."""
        return len(self.coordinator.get_device_summary()["outdated"]) > 0

    async def async_press(self) -> None:
        """Update all outdated devices."""
        outdated_entities = [
            entity
            for entity in self.coordinator.entities.values()
            if entity.installed_version
            and entity.latest_version
            and entity.installed_version != entity.latest_version
        ]

        _LOGGER.info(
            "Starting batch manual update for %d OpenBeken devices (backup=%s)",
            len(outdated_entities),
            self._with_backup,
        )

        for entity in outdated_entities:
            try:
                await entity.async_install(backup=self._with_backup)
            except Exception as err:
                _LOGGER.error(
                    "Failed to update %s during batch update: %s",
                    entity.device_name,
                    err,
                )

        self.coordinator.async_update_listeners()
