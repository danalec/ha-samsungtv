"""Base SamsungTV Entity."""

import re
from functools import partial
from typing import Any, override

from homeassistant.const import CONF_HOST, CONF_MAC, CONF_MODEL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.trigger import PluggableAction
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from wakeonlan import send_magic_packet

from .const import CONF_MANUFACTURER, DOMAIN, LOGGER
from .coordinator import SamsungTVDataUpdateCoordinator
from .triggers.turn_on import async_get_turn_on_trigger

# A MAC is six hex bytes. The config flow stores whatever the TV reported, so
# accept any of the separator styles rather than assuming one.
MAC_RE = re.compile(r"^[0-9a-fA-F]{2}([:-]?)(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}$")


def is_valid_mac(mac: str | None) -> bool:
    """Return True when the string can be turned into a magic packet."""
    return bool(mac) and bool(MAC_RE.match(mac))  # type: ignore[arg-type]


class SamsungTVEntity(CoordinatorEntity[SamsungTVDataUpdateCoordinator], Entity):
    """Defines a base SamsungTV entity."""

    _attr_has_entity_name = True

    def __init__(self, *, coordinator: SamsungTVDataUpdateCoordinator) -> None:
        """Initialize the SamsungTV entity."""
        super().__init__(coordinator)
        self._bridge = coordinator.bridge
        config_entry = coordinator.config_entry
        self._mac: str | None = config_entry.data.get(CONF_MAC)
        self._host: str | None = config_entry.data.get(CONF_HOST)
        # Fallback for legacy models that doesn't have a API
        # to retrieve MAC or SerialNumber
        self._attr_unique_id = config_entry.unique_id or config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            manufacturer=config_entry.data.get(CONF_MANUFACTURER),
            model_id=config_entry.data.get(CONF_MODEL),
        )
        if self.unique_id:
            self._attr_device_info.identifiers = {(DOMAIN, self.unique_id)}
        if self._mac:
            self._attr_device_info.connections = {
                (dr.CONNECTION_NETWORK_MAC, self._mac)
            }
        self._turn_on_action = PluggableAction(self.async_write_ha_state)

    @property
    @override
    def available(self) -> bool:
        """Return the availability of the device."""
        if not super().available or self._bridge.auth_failed:
            return False
        return (
            self.coordinator.is_on
            or bool(self._turn_on_action)
            or self._mac is not None
            or self._bridge.power_off_in_progress
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Connect and subscribe to dispatcher signals and state updates."""
        await super().async_added_to_hass()

        if (entry := self.registry_entry) and entry.device_id:
            self.async_on_remove(
                self._turn_on_action.async_register(
                    self.hass, async_get_turn_on_trigger(entry.device_id)
                )
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self._bridge.async_power_off()
        await self.coordinator.async_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the remote on.

        This method is not upstream: see AGENTS.md. Samsung TVs are commonly
        documented as ignoring wake-on-LAN, but that does not hold for the Neo
        QLED family, where a magic packet wakes the TV from deep standby. The
        packet is sent when a usable MAC is known, and the turn-on automation
        runs afterwards when one is attached, so a setup that already relied on
        the automation keeps working unchanged.
        """
        if is_valid_mac(self._mac):
            mac = self._mac
            LOGGER.debug("Sending a wake-on-lan packet to %s (%s)", mac, self._host)
            await self.hass.async_add_executor_job(partial(send_magic_packet, mac))
        else:
            mac = None

        if self._turn_on_action:
            LOGGER.debug("Attempting to turn on %s via automation", self.entity_id)
            await self._turn_on_action.async_run(self.hass, self._context)
            return

        if mac:
            return

        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="service_unsupported",
            translation_placeholders={"entity": self.entity_id},
        )
