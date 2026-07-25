"""Data models for the Nature Remo Cloud API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp, returning None when absent or invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Rate limit state reported by the API response headers."""

    limit: int | None
    remaining: int | None
    reset: int | None


@dataclass(frozen=True, slots=True)
class User:
    """A Nature account."""

    id: str
    nickname: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        """Build from an API payload."""
        return cls(id=str(data["id"]), nickname=str(data.get("nickname") or ""))


EVENT_TEMPERATURE = "te"
EVENT_HUMIDITY = "hu"
EVENT_ILLUMINATION = "il"
EVENT_MOVEMENT = "mo"


@dataclass(frozen=True, slots=True)
class SensorValue:
    """A single sensor reading from newest_events."""

    value: float
    created_at: datetime | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SensorValue:
        """Build from an API payload."""
        return cls(
            value=float(data["val"]),
            created_at=_parse_datetime(data.get("created_at")),
        )


@dataclass(frozen=True, slots=True)
class Device:
    """A Nature Remo hardware device."""

    id: str
    name: str
    temperature_offset: float
    humidity_offset: float
    firmware_version: str
    mac_address: str | None
    bt_mac_address: str | None
    serial_number: str | None
    online: bool | None
    events: dict[str, SensorValue]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        """Build from an API payload; unknown event keys are kept as-is.

        online is only reported by newer firmware; None means "not
        reported" (old firmware omits the field), never "offline".
        """
        raw_events = data.get("newest_events") or {}
        events = {
            key: SensorValue.from_dict(value)
            for key, value in raw_events.items()
            if isinstance(value, dict) and "val" in value
        }
        raw_online = data.get("online")
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or ""),
            temperature_offset=float(data.get("temperature_offset") or 0),
            humidity_offset=float(data.get("humidity_offset") or 0),
            firmware_version=str(data.get("firmware_version") or ""),
            mac_address=data.get("mac_address"),
            bt_mac_address=data.get("bt_mac_address"),
            serial_number=data.get("serial_number"),
            online=raw_online if isinstance(raw_online, bool) else None,
            events=events,
        )


@dataclass(frozen=True, slots=True)
class ApplianceModel:
    """Metadata about the appliance's remote/model."""

    id: str
    manufacturer: str | None
    remote_name: str | None
    series: str | None
    name: str | None
    image: str | None
    country: str | None
    slug: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplianceModel:
        """Build from an API payload."""
        return cls(
            id=str(data.get("id") or ""),
            manufacturer=data.get("manufacturer"),
            remote_name=data.get("remote_name"),
            series=data.get("series"),
            name=data.get("name"),
            image=data.get("image"),
            country=data.get("country"),
            slug=data.get("slug"),
        )


def _str_list(value: Any) -> list[str]:
    """Coerce an optional list of values into a list of non-empty strings.

    The API sends unsupported ranges (e.g. dirh on ACs without horizontal
    swing) as a single-item placeholder like [""] rather than omitting the
    key, so blank entries must be dropped to represent "not supported".
    """
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


@dataclass(frozen=True, slots=True)
class AirconModeRange:
    """Allowed setting values for one AC operation mode."""

    temperatures: list[str]
    volumes: list[str]
    directions: list[str]
    directions_h: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirconModeRange:
        """Build from an API payload."""
        return cls(
            temperatures=_str_list(data.get("temp")),
            volumes=_str_list(data.get("vol")),
            directions=_str_list(data.get("dir")),
            directions_h=_str_list(data.get("dirh")),
        )


@dataclass(frozen=True, slots=True)
class AirconExtraOption:
    """One selectable value of a device-specific AC parameter."""

    value: str
    text: str
    default: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirconExtraOption:
        """Build from an API payload."""
        return cls(
            value=str(data["value"]),
            text=str(data.get("text") or ""),
            default=bool(data.get("default", False)),
        )


@dataclass(frozen=True, slots=True)
class AirconExtra:
    """A device-specific AC parameter (e.g. autoclean) and its options.

    Sent to the API as an extra.= form field. Observed type vocabulary is
    "choice" (with options) and "time" (with default_time instead of
    options, written as HH:MM). Observed availability vocabulary is
    "available" and "hidden"; hidden means not usable in the current
    operation mode — writes of hidden extras return 200 but are silently
    ignored server-side.
    """

    id: str
    text: str
    description: str
    type: str
    availability: str
    options: list[AirconExtraOption]
    default_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirconExtra:
        """Build from an API payload."""
        return cls(
            id=str(data["id"]),
            text=str(data.get("text") or ""),
            description=str(data.get("description") or ""),
            type=str(data.get("type") or ""),
            availability=str(data.get("availability") or ""),
            options=[
                AirconExtraOption.from_dict(item)
                for item in data.get("options") or []
                if isinstance(item, dict) and "value" in item
            ],
            default_time=data.get("defaultTime"),
        )


@dataclass(frozen=True, slots=True)
class Aircon:
    """AC capabilities."""

    modes: dict[str, AirconModeRange]
    fixed_buttons: list[str]
    temp_unit: str
    extras: list[AirconExtra] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build from an API payload."""
        range_data = data.get("range") or {}
        modes_data = range_data.get("modes") or {}
        return cls(
            modes={
                str(mode): AirconModeRange.from_dict(mode_range or {})
                for mode, mode_range in modes_data.items()
            },
            fixed_buttons=_str_list(range_data.get("fixedButtons")),
            temp_unit=str(data.get("tempUnit") or ""),
            extras=[
                AirconExtra.from_dict(item)
                for item in range_data.get("extras") or []
                if isinstance(item, dict) and "id" in item
            ],
        )


@dataclass(frozen=True, slots=True)
class FloorHeater(Aircon):
    """Floor heater capabilities.

    The API's floor_heater capability object has exactly the aircon shape
    (range.modes / range.fixedButtons / range.extras plus tempUnit;
    probe-verified against a Corona rfc-a04), so this is a marker subclass
    of Aircon with no additional fields.
    """


@dataclass(frozen=True, slots=True)
class AirconSettings:
    """Current AC settings; button == "power-off" means the AC is off."""

    temperature: str
    temperature_unit: str
    mode: str
    volume: str
    direction: str
    direction_h: str
    button: str
    updated_at: datetime | None
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirconSettings:
        """Build from an API payload."""
        return cls(
            temperature=str(data.get("temp") or ""),
            temperature_unit=str(data.get("temp_unit") or ""),
            mode=str(data.get("mode") or ""),
            volume=str(data.get("vol") or ""),
            direction=str(data.get("dir") or ""),
            direction_h=str(data.get("dirh") or ""),
            button=str(data.get("button") or ""),
            updated_at=_parse_datetime(data.get("updated_at")),
            extra={
                str(key): str(value) for key, value in (data.get("extra") or {}).items()
            },
        )


@dataclass(frozen=True, slots=True)
class ApplianceButton:
    """A named IR button on a TV or LIGHT appliance."""

    name: str
    label: str
    image: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplianceButton:
        """Build from an API payload."""
        return cls(
            name=str(data.get("name") or ""),
            label=str(data.get("label") or ""),
            image=str(data.get("image") or ""),
        )


@dataclass(frozen=True, slots=True)
class TVState:
    """Current TV state."""

    input: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TVState:
        """Build from an API payload."""
        return cls(input=data.get("input"))


@dataclass(frozen=True, slots=True)
class TV:
    """A TV appliance."""

    buttons: list[ApplianceButton]
    state: TVState

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TV:
        """Build from an API payload."""
        return cls(
            buttons=[
                ApplianceButton.from_dict(button)
                for button in data.get("buttons") or []
            ],
            state=TVState.from_dict(data.get("state") or {}),
        )


@dataclass(frozen=True, slots=True)
class LightState:
    """Current light state."""

    brightness: str | None
    power: str | None
    last_button: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LightState:
        """Build from an API payload."""
        return cls(
            brightness=data.get("brightness"),
            power=data.get("power"),
            last_button=data.get("last_button"),
        )


@dataclass(frozen=True, slots=True)
class Light:
    """A LIGHT appliance."""

    buttons: list[ApplianceButton]
    state: LightState

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Light:
        """Build from an API payload."""
        return cls(
            buttons=[
                ApplianceButton.from_dict(button)
                for button in data.get("buttons") or []
            ],
            state=LightState.from_dict(data.get("state") or {}),
        )


@dataclass(frozen=True, slots=True)
class LightProjectorButton:
    """A button leaf in a LIGHT_PROJECTOR remote layout.

    Unlike TV/LIGHT buttons, the display text lives in the "text" field
    ("label" is empty in real payloads).
    """

    name: str
    text: str
    image: str
    uuid: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LightProjectorButton:
        """Build from an API payload."""
        return cls(
            name=str(data.get("name") or ""),
            text=str(data.get("text") or ""),
            image=str(data.get("image") or ""),
            uuid=str(data.get("uuid") or ""),
        )


def _collect_layout_buttons(node: Any, buttons: list[LightProjectorButton]) -> None:
    """Collect type=="button" leaves from a layout tree in document order."""
    if not isinstance(node, dict):
        return
    if node.get("type") == "button":
        button = LightProjectorButton.from_dict(node)
        if button.name:
            buttons.append(button)
        return
    for child in node.get("templates") or []:
        _collect_layout_buttons(child, buttons)


@dataclass(frozen=True, slots=True)
class LightProjector:
    """A LIGHT_PROJECTOR appliance's virtual remote, flattened to buttons.

    The API describes the remote as a UI layout tree (root → template /
    composite nodes → button leaves) rather than a buttons[] array; only
    the button leaves matter for control, so the tree is flattened in
    document order, skipping unnamed leaves.
    """

    buttons: list[LightProjectorButton]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LightProjector:
        """Build from the light_projector payload, walking its layout tree."""
        buttons: list[LightProjectorButton] = []
        _collect_layout_buttons(data.get("layout") or {}, buttons)
        return cls(buttons=buttons)


@dataclass(frozen=True, slots=True)
class Signal:
    """A learned IR signal."""

    id: str
    name: str
    image: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        """Build from an API payload."""
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or ""),
            image=str(data.get("image") or ""),
        )


EPC_COEFFICIENT = 211
EPC_EFFECTIVE_DIGITS = 215
EPC_NORMAL_CUMULATIVE_ENERGY = 224
EPC_CUMULATIVE_ENERGY_UNIT = 225
EPC_REVERSE_CUMULATIVE_ENERGY = 227
EPC_INSTANTANEOUS_POWER = 231

# ECHONET Lite EPC 0xE1 unit codes. Codes 10-13 MULTIPLY; a 10^-n shortcut
# formula is wrong for them, so this must stay a lookup table.
ENERGY_UNIT_MULTIPLIERS: dict[int, float] = {
    0: 1.0,
    1: 0.1,
    2: 0.01,
    3: 0.001,
    4: 0.0001,
    10: 10.0,
    11: 100.0,
    12: 1000.0,
    13: 10000.0,
}


@dataclass(frozen=True, slots=True)
class EchonetLiteProperty:
    """A raw ECHONET Lite property exposed by a smart meter."""

    name: str
    epc: int
    value: str
    updated_at: datetime | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EchonetLiteProperty:
        """Build from an API payload."""
        return cls(
            name=str(data.get("name") or ""),
            epc=int(data["epc"]),
            value=str(data.get("val") or ""),
            updated_at=_parse_datetime(data.get("updated_at")),
        )


@dataclass(frozen=True, slots=True)
class SmartMeter:
    """An ECHONET Lite smart meter paired with a Nature Remo E."""

    properties: list[EchonetLiteProperty]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SmartMeter:
        """Build from an API payload."""
        return cls(
            properties=[
                EchonetLiteProperty.from_dict(item)
                for item in data.get("echonetlite_properties") or []
                if isinstance(item, dict) and "epc" in item
            ]
        )

    def _int_property(self, epc: int) -> int | None:
        """Return an EPC value as int, or None when absent/invalid."""
        for prop in self.properties:
            if prop.epc == epc:
                try:
                    return int(prop.value)
                except ValueError:
                    return None
        return None

    @property
    def instantaneous_power_w(self) -> int | None:
        """Instantaneous power in watts (negative = exporting)."""
        return self._int_property(EPC_INSTANTANEOUS_POWER)

    def _cumulative_kwh(self, epc: int) -> float | None:
        """Scale a raw cumulative counter into kWh."""
        raw = self._int_property(epc)
        unit_code = self._int_property(EPC_CUMULATIVE_ENERGY_UNIT)
        if raw is None or unit_code is None:
            return None
        multiplier = ENERGY_UNIT_MULTIPLIERS.get(unit_code)
        if multiplier is None:
            return None
        coefficient = self._int_property(EPC_COEFFICIENT)
        if coefficient is None:
            coefficient = 1
        return round(raw * coefficient * multiplier, 4)

    @property
    def cumulative_energy_kwh(self) -> float | None:
        """Cumulative purchased energy in kWh."""
        return self._cumulative_kwh(EPC_NORMAL_CUMULATIVE_ENERGY)

    @property
    def cumulative_energy_reverse_kwh(self) -> float | None:
        """Cumulative sold energy in kWh."""
        return self._cumulative_kwh(EPC_REVERSE_CUMULATIVE_ENERGY)


APPLIANCE_TYPE_AC = "AC"
APPLIANCE_TYPE_TV = "TV"
APPLIANCE_TYPE_LIGHT = "LIGHT"
APPLIANCE_TYPE_IR = "IR"
APPLIANCE_TYPE_SMART_METER = "EL_SMART_METER"
APPLIANCE_TYPE_FLOOR_HEATER = "FLOOR_HEATER"
APPLIANCE_TYPE_LIGHT_PROJECTOR = "LIGHT_PROJECTOR"


@dataclass(frozen=True, slots=True)
class Appliance:
    """An appliance registered on a Nature Remo device."""

    id: str
    type: str
    nickname: str
    image: str
    device_id: str | None
    model: ApplianceModel | None
    settings: AirconSettings | None
    aircon: Aircon | None
    floor_heater: FloorHeater | None
    tv: TV | None
    light: Light | None
    light_projector: LightProjector | None
    smart_meter: SmartMeter | None
    signals: list[Signal]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Appliance:
        """Build from an API payload; absent sub-objects stay None."""
        device = data.get("device") or {}
        return cls(
            id=str(data["id"]),
            type=str(data.get("type") or ""),
            nickname=str(data.get("nickname") or ""),
            image=str(data.get("image") or ""),
            device_id=str(device["id"]) if device.get("id") else None,
            model=(
                ApplianceModel.from_dict(data["model"]) if data.get("model") else None
            ),
            settings=(
                AirconSettings.from_dict(data["settings"])
                if data.get("settings")
                else None
            ),
            aircon=Aircon.from_dict(data["aircon"]) if data.get("aircon") else None,
            floor_heater=(
                FloorHeater.from_dict(data["floor_heater"])
                if data.get("floor_heater")
                else None
            ),
            tv=TV.from_dict(data["tv"]) if data.get("tv") else None,
            light=Light.from_dict(data["light"]) if data.get("light") else None,
            light_projector=(
                LightProjector.from_dict(data["light_projector"])
                if data.get("light_projector")
                else None
            ),
            smart_meter=(
                SmartMeter.from_dict(data["smart_meter"])
                if data.get("smart_meter")
                else None
            ),
            signals=[
                Signal.from_dict(item)
                for item in data.get("signals") or []
                if isinstance(item, dict) and "id" in item
            ],
        )
