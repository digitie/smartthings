"""Support for switches through the SmartThings cloud API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple
from typing import Any

from pysmartthings import Attribute, Capability
from pysmartthings.device import DeviceEntity

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmartThingsEntity
from .const import DATA_BROKERS, DOMAIN

class Map(NamedTuple):
    """Tuple for mapping Smartthings capabilities to Home Assistant sensors."""

    attribute: str
    on_command: str
    off_command: str
    on_value: str
    off_value: str
    name: str
    icon: str | None


CAPABILITY_TO_SWITCH: dict[str, list[Map]] = {
    Capability.switch: [
        Map(
            Attribute.switch,
            "switch_on",
            "switch_off",
            "on",
            "off",
            "Switch",
            None,
            None,
        )
    ],
    "custom.spiMode": [
        Map(
            "spiMode",
            "setSpiMode",
            "setSpiMode",
            "on",
            "off",
            "SPI Mode",
            None,
            None,
        )
    ],
    "custom.autoCleaningMode": [
        Map(
            "autoCleaningMode",
            "setAutoCleaningMode",
            "setAutoCleaningMode",
            "on",
            "off",
            "Auto Cleaning Mode",
            "mdi:shimmer",
            None,
        )
    ],
    "samsungce.alwaysOnSensing": [
        Map(
            "alwaysOnSensing",
            "on",
            "off",
            "devicePlugin",
            "devicePlugin",
            "Always On Sensing",
            "mdi:shimmer",
            None,
        )
    ],
    "samsungce.dehumidifierBeep": [
        Map(
            "dehumidifierBeep",
            "on",
            "off",
            None,
            None,
            "Beep",
            "mdi:speaker",
            None,
        )
    ],
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switches for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    switches = []
    for device in broker.devices.values():
        for capability in broker.get_assigned(device.device_id, "switch"):
            maps = CAPABILITY_TO_SWITCH[capability]
            if capability in ("custom.autoCleaningMode", "custom.spiMode", "samsungce.alwaysOnSensing", "samsungce.dehumidifierBeep"):
                switches.extend(
                    [
                        SmartThingsCustomSwitch(
                            device,
                            capability,
                            m.attribute,
                            m.on_command,
                            m.off_command,
                            m.on_value,
                            m.off_value,
                            m.name,
                            m.icon,
                            m.extra_state_attributes,
                        )
                        for m in maps
                    ]
                )
            else:
                switches.extend([SmartThingsSwitch(device)])

        if (
            device.status.attributes[Attribute.mnmn].value == "Samsung Electronics"
            and device.type == "OCF"
        ):
            model = device.status.attributes[Attribute.mnmo].value.split("|")[0]
            if (
                Capability.execute
                and broker.any_assigned(device.device_id, "climate")
                and model
                not in (
                    "SAC_SLIM1WAY",
                    "SAC_BIG_SLIM1WAY",
                    "MIM-H04EN",
                )
            ):
                switches.extend(
                    [
                        SamsungOcfSwitch(
                            device,
                            "/mode/vs/0",
                            "x.com.samsung.da.options",
                            ["Light_Off"],
                            ["Light_On"],
                            "Light",
                            "mdi:led-on",
                            "mdi:led-variant-off",
                        )
                    ]
                )
            elif model in ("TP2X_DA-KS-RANGE-0101X",):
                switches.extend(
                    [
                        SamsungOcfSwitch(
                            device,
                            "/mode/vs/0",
                            "x.com.samsung.da.options",
                            ["Sound_On"],
                            ["Sound_Off"],
                            "Sound",
                            "mdi:volume-high",
                            "mdi:volume-variant-off",
                        )
                    ]
                )
            elif model in ("21K_REF_LCD_FHUB6.0", "ARTIK051_REF_17K"):
                switches.extend(
                    [
                        SamsungOcfSwitch(
                            device,
                            "/refrigeration/vs/0",
                            "x.com.samsung.da.rapidFridge",
                            "On",
                            "Off",
                            "Power Cool",
                            "mdi:fridge-outline",
                            "mdi:fridge-outline",
                        ),
                        SamsungOcfSwitch(
                            device,
                            "/refrigeration/vs/0",
                            "x.com.samsung.da.rapidFreezing",
                            "On",
                            "Off",
                            "Power Freeze",
                            "mdi:fridge-outline",
                            "mdi:fridge-outline",
                        ),
                        SamsungOcfSwitch(
                            device,
                            "/icemaker/status/vs/0",
                            "x.com.samsung.da.iceMaker",
                            "On",
                            "Off",
                            "Ice Maker",
                            "mdi:delete-variant",
                            "mdi:delete-variant",
                        ),
                    ]
                )

    async_add_entities(switches)


def get_capabilities(capabilities: Sequence[str]) -> Sequence[str] | None:
    """Return all capabilities supported if minimum required are present."""
    # Must be able to be turned on/off.
    return [
        capability for capability in CAPABILITY_TO_SWITCH if capability in capabilities
    ]
    #if Capability.switch in capabilities:
    #    return [Capability.switch, Capability.energy_meter, Capability.power_meter]
    #return None


class SmartThingsSwitch(SmartThingsEntity, SwitchEntity):
    """Define a SmartThings switch."""

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._device.switch_off(set_status=True)
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._device.switch_on(set_status=True)
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._device.status.switch


class SmartThingsCustomSwitch(SmartThingsEntity, SwitchEntity):
    """Define a SmartThings custom switch."""

    def __init__(
        self,
        device: DeviceEntity,
        capability: str,
        attribute: str,
        on_command: str,
        off_command: str,
        on_value: str | int | None,
        off_value: str | int | None,
        name: str,
        icon: str | None,
        extra_state_attributes: str | None,
    ) -> None:
        """Init the class."""
        super().__init__(device)
        self._capability = capability
        self._attribute = attribute
        self._on_command = on_command
        self._off_command = off_command
        self._on_value = on_value
        self._off_value = off_value
        self._name = name
        self._icon = icon
        self._extra_state_attributes = extra_state_attributes

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        result = await self._device.command(
            "main", self._capability, self._off_command, None if self._off_value == None else [self._off_value]
        )
        if result:
            self._device.status.update_attribute_value(self._attribute, "off")
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        result = await self._device.command(
            "main", self._capability, self._on_command, None if self._on_value == None else [self._on_value]
        )
        if result:
            self._device.status.update_attribute_value(self._attribute, "on")

        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self._device.label} {self._name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._device.device_id}.{self._attribute}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        if self._on_value is not None:
            if self._device.status.attributes[self._attribute].value == self._on_value:
                return True
            return False
        return self._device.status.attributes[self._attribute].value
        # return True if getattr(self._device.status, self._attribute) == "on" else False
        
    @property
    def icon(self) -> str | None:
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        state_attributes = {}
        if self._extra_state_attributes is not None:
            attributes = self._extra_state_attributes
            for attribute in attributes:
                value = self._device.status.attributes[attribute].value
                if value is not None:
                    state_attributes[attribute] = value
        return state_attributes


class SamsungOcfSwitch(SmartThingsEntity, SwitchEntity):
    """add samsung ocf switch"""

    def __init__(
        self,
        device: DeviceEntity,
        page: str,
        key: str,
        on_value: str | list[str],
        off_value: str | list[str],
        name: str,
        on_icon: str | None,
        off_icon: str | None,
    ) -> None:
        """Init the class."""
        super().__init__(device)
        self._page = page
        self._key = key
        self._on_value = on_value
        self._off_value = off_value
        self._name = name
        self._on_icon = on_icon
        self._off_icon = off_icon

    execute_state = False
    init_bool = False

    def startup(self):
        """Make sure that OCF page visits mode on startup"""
        tasks = []
        tasks.append(self._device.execute(self._page))
        asyncio.gather(*tasks)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        result = await self._device.execute(self._page, {self._key: self._off_value})
        if result:
            self._device.status.update_attribute_value(
                "data", {"payload": {self._key: self._off_value}}
            )
            self.execute_state = False
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        result = await self._device.execute(self._page, {self._key: self._on_value})
        if result:
            self._device.status.update_attribute_value(
                "data", {"payload": {self._key: self._on_value}}
            )
            self.execute_state = True
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the light switch."""
        return f"{self._device.label} {self._name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        _unique_id = self._name.lower().replace(" ", "_")
        return f"{self._device.device_id}.{_unique_id}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        if not self.init_bool:
            self.startup()
        if self._device.status.attributes[Attribute.data].data["href"] == self._page:
            self.init_bool = True
            output = self._device.status.attributes[Attribute.data].value["payload"][
                self._key
            ]
            if len(self._on_value) > 1:
                if self._on_value in output:
                    self.execute_state = True
                elif self._off_value in output:
                    self.execute_state = False
            else:
                if self._on_value[0] in output:
                    self.execute_state = True
                elif self._off_value[0] in output:
                    self.execute_state = False
        return self.execute_state

    @property
    def icon(self) -> str | None:
        if self.is_on:
            return self._on_icon
        return self._off_icon
