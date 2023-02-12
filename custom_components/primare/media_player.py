"""Support for interfacing with PRIMARE receivers through RS-232."""
from __future__ import annotations

from primare_preamp import PrimarePreamp, PrimarePreampTCP, PrimarePreampTelnet
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

DEFAULT_TYPE = "RS232"
DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_PORT = 53
DEFAULT_NAME = "Primare preamp"
DEFAULT_MIN_VOLUME = -92
DEFAULT_MAX_VOLUME = -20
DEFAULT_VOLUME_STEP = 4

SUPPORT_PRIMARE = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

CONF_SERIAL_PORT = "serial_port"  # for PrimarePreamp
CONF_MIN_VOLUME = "min_volume"
CONF_MAX_VOLUME = "max_volume"
CONF_VOLUME_STEP = "volume_step"  # for PrimarePreampTCP
CONF_SOURCE_DICT = "sources"  # for PrimarePreamp

# Max value based on a C658 with an MDC HDM-2 card installed
SOURCE_DICT_SCHEMA = vol.Schema({vol.Range(min=1, max=12): cv.string})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_TYPE, default=DEFAULT_TYPE): vol.In(
            ["RS232", "Telnet", "TCP"]
        ),
        vol.Optional(CONF_SERIAL_PORT, default=DEFAULT_SERIAL_PORT): cv.string,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MIN_VOLUME, default=DEFAULT_MIN_VOLUME): int,
        vol.Optional(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): int,
        vol.Optional(CONF_SOURCE_DICT, default={}): SOURCE_DICT_SCHEMA,
        vol.Optional(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): int,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Primare platform."""
    if config.get(CONF_TYPE) in ("RS232", "Telnet"):
        add_entities(
            [Primare(config)],
            True,
        )
    else:
        add_entities(
            [Primaretcp(config)],
            True,
        )


class Primare(MediaPlayerEntity):
    """Representation of a Primare preamp."""

    _attr_icon = "mdi:speaker-multiple"
    _attr_supported_features = SUPPORT_PRIMARE

    def __init__(self, config):
        """Initialize the Primare preamp device."""
        self.config = config
        self._instantiate_primare_preamp()
        self._attr_name = self.config[CONF_NAME]
        self._min_volume = config[CONF_MIN_VOLUME]
        self._max_volume = config[CONF_MAX_VOLUME]
        self._source_dict = config[CONF_SOURCE_DICT]
        self._reverse_mapping = {value: key for key, value in self._source_dict.items()}

    def _instantiate_primare_preamp(self) -> PrimarePreamp:
        if self.config[CONF_TYPE] == "RS232":
            self._primare_preamp = PrimarePreamp(self.config[CONF_SERIAL_PORT])
        else:
            host = self.config.get(CONF_HOST)
            port = self.config[CONF_PORT]
            self._primare_preamp = PrimarePreampTelnet(host, port)

    def turn_off(self) -> None:
        """Turn the media player off."""
        self._primare_preamp.main_power("=", "Off")

    def turn_on(self) -> None:
        """Turn the media player on."""
        self._primare_preamp.main_power("=", "On")

    def volume_up(self) -> None:
        """Volume up the media player."""
        self._primare_preamp.main_volume("+")

    def volume_down(self) -> None:
        """Volume down the media player."""
        self._primare_preamp.main_volume("-")

    def set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        self._primare_preamp.main_volume("=", self.calc_db(volume))

    def mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        if mute:
            self._primare_preamp.main_mute("=", "On")
        else:
            self._primare_preamp.main_mute("=", "Off")

    def select_source(self, source: str) -> None:
        """Select input source."""
        self._primare_preamp.main_source("=", self._reverse_mapping.get(source))

    @property
    def source_list(self):
        """List of available input sources."""
        return sorted(self._reverse_mapping)

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self.state is not None

    def update(self) -> None:
        """Retrieve latest state."""
        power_state = self._primare_preamp.main_power("?")
        if not power_state:
            self._attr_state = None
            return
        self._attr_state = (
            MediaPlayerState.ON
            if self._primare_preamp.main_power("?") == "On"
            else MediaPlayerState.OFF
        )

        if self.state == MediaPlayerState.ON:
            self._attr_is_volume_muted = self._primare_preamp.main_mute("?") == "On"
            volume = self._primare_preamp.main_volume("?")
            # Some receivers cannot report the volume, e.g. C 356BEE,
            # instead they only support stepping the volume up or down
            self._attr_volume_level = (
                self.calc_volume(volume) if volume is not None else None
            )
            self._attr_source = self._source_dict.get(
                self._primare_preamp.main_source("?")
            )

    def calc_volume(self, decibel):
        """Calculate the volume given the decibel.

        Return the volume (0..1).
        """
        return abs(self._min_volume - decibel) / abs(
            self._min_volume - self._max_volume
        )

    def calc_db(self, volume):
        """Calculate the decibel given the volume.

        Return the dB.
        """
        return self._min_volume + round(
            abs(self._min_volume - self._max_volume) * volume
        )


class Primaretcp(MediaPlayerEntity):
    """Representation of a Primare Digital amplifier."""

    _attr_supported_features = SUPPORT_PRIMARE

    def __init__(self, config):
        """Initialize the amplifier."""
        self._attr_name = config[CONF_NAME]
        self._primare_preamp = PrimarePreampTCP(config.get(CONF_HOST))
        self._min_vol = (config[CONF_MIN_VOLUME] + 90) * 2  # from dB to nad vol (0-200)
        self._max_vol = (config[CONF_MAX_VOLUME] + 90) * 2  # from dB to nad vol (0-200)
        self._volume_step = config[CONF_VOLUME_STEP]
        self._nad_volume = None
        self._source_list = self._primare_preamp.available_sources()

    def turn_off(self) -> None:
        """Turn the media player off."""
        self._primare_preamp.power_off()

    def turn_on(self) -> None:
        """Turn the media player on."""
        self._primare_preamp.power_on()

    def volume_up(self) -> None:
        """Step volume up in the configured increments."""
        self._primare_preamp.set_volume(self._nad_volume + 2 * self._volume_step)

    def volume_down(self) -> None:
        """Step volume down in the configured increments."""
        self._primare_preamp.set_volume(self._nad_volume - 2 * self._volume_step)

    def set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        nad_volume_to_set = int(
            round(volume * (self._max_vol - self._min_vol) + self._min_vol)
        )
        self._primare_preamp.set_volume(nad_volume_to_set)

    def mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        if mute:
            self._primare_preamp.mute()
        else:
            self._primare_preamp.unmute()

    def select_source(self, source: str) -> None:
        """Select input source."""
        self._primare_preamp.select_source(source)

    @property
    def source_list(self):
        """List of available input sources."""
        return self._primare_preamp.available_sources()

    def update(self) -> None:
        """Get the latest details from the device."""
        try:
            nad_status = self._primare_preamp.status()
        except OSError:
            return
        if nad_status is None:
            return

        # Update on/off state
        if nad_status["power"]:
            self._attr_state = MediaPlayerState.ON
        else:
            self._attr_state = MediaPlayerState.OFF

        # Update current volume
        self._attr_volume_level = self.nad_vol_to_internal_vol(nad_status["volume"])
        self._nad_volume = nad_status["volume"]

        # Update muted state
        self._attr_is_volume_muted = nad_status["muted"]

        # Update current source
        self._attr_source = nad_status["source"]

    def nad_vol_to_internal_vol(self, nad_volume):
        """Convert nad volume range (0-200) to internal volume range.

        Takes into account configured min and max volume.
        """
        if nad_volume < self._min_vol:
            volume_internal = 0.0
        elif nad_volume > self._max_vol:
            volume_internal = 1.0
        else:
            volume_internal = (nad_volume - self._min_vol) / (
                self._max_vol - self._min_vol
            )
        return volume_internal
