"""Sensor platform for OpenBeken OTA status overview."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenBekenReleaseCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenBeken OTA summary sensors."""
    coordinator: OpenBekenReleaseCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OpenBekenUpToDateSensor(coordinator, entry.entry_id),
            OpenBekenOutdatedSensor(coordinator, entry.entry_id),
        ]
    )


class OpenBekenUpToDateSensor(
    CoordinatorEntity[OpenBekenReleaseCoordinator], SensorEntity
):
    """Sensor showing count and list of up-to-date OpenBeken devices."""

    _attr_name = "OpenBeken Ajan tasalla"
    _attr_icon = "mdi:check-circle-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: OpenBekenReleaseCoordinator, entry_id: str
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_up_to_date_count"

    @property
    def native_value(self) -> int:
        """Return count of up-to-date devices."""
        return len(self.coordinator.get_device_summary()["up_to_date"])

    @property
    def extra_state_attributes(self) -> dict:
        """Return list of up-to-date device names and versions."""
        devices = self.coordinator.get_device_summary()["up_to_date"]
        return {
            "devices": [d["name"] for d in devices],
            "details": devices,
        }


class OpenBekenOutdatedSensor(
    CoordinatorEntity[OpenBekenReleaseCoordinator], SensorEntity
):
    """Sensor showing count and list of OpenBeken devices requiring an update."""

    _attr_name = "OpenBeken Vaatii päivityksen"
    _attr_icon = "mdi:update"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: OpenBekenReleaseCoordinator, entry_id: str
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_outdated_count"

    @property
    def native_value(self) -> int:
        """Return count of outdated devices."""
        return len(self.coordinator.get_device_summary()["outdated"])

    @property
    def extra_state_attributes(self) -> dict:
        """Return list of outdated device names and version info."""
        devices = self.coordinator.get_device_summary()["outdated"]
        return {
            "devices": [d["name"] for d in devices],
            "details": devices,
        }