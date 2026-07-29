"""Tests for model parsing."""

from datetime import UTC, datetime

from aionatureremo import (
    TV,
    Aircon,
    AirconExtra,
    AirconModeRange,
    AirconSettings,
    Appliance,
    ApplianceModel,
    Device,
    EchonetLiteAppliance,
    FloorHeater,
    Light,
    LightProjector,
    Signal,
    SmartMeter,
)

DEVICE_PAYLOAD = {
    "id": "device-1",
    "name": "Living Remo",
    "temperature_offset": 1,
    "humidity_offset": -2,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2026-07-01T00:00:00Z",
    "mac_address": "ab:cd:ef:12:34:56",
    "bt_mac_address": "ab:cd:ef:12:34:57",
    "serial_number": "1W123456789012",
    "firmware_version": "Remo/1.14.8",
    "newest_events": {
        "te": {"val": 26.4, "created_at": "2026-07-18T07:59:00Z"},
        "hu": {"val": 52, "created_at": "2026-07-18T07:59:00Z"},
        "il": {"val": 123.4, "created_at": "2026-07-18T07:58:00Z"},
        "mo": {"val": 1, "created_at": "2026-07-18T07:50:00Z"},
    },
}


def test_device_from_dict_full() -> None:
    """All fields and events parse."""
    device = Device.from_dict(DEVICE_PAYLOAD)

    assert device.id == "device-1"
    assert device.name == "Living Remo"
    assert device.temperature_offset == 1.0
    assert device.humidity_offset == -2.0
    assert device.firmware_version == "Remo/1.14.8"
    assert device.mac_address == "ab:cd:ef:12:34:56"
    assert device.serial_number == "1W123456789012"
    assert device.events["te"].value == 26.4
    assert device.events["mo"].created_at == datetime(2026, 7, 18, 7, 50, tzinfo=UTC)


def test_device_from_dict_minimal() -> None:
    """A device without events (e.g. Remo E lite) parses with defaults."""
    device = Device.from_dict({"id": "device-2", "name": "Remo E lite"})

    assert device.events == {}
    assert device.temperature_offset == 0.0
    assert device.mac_address is None


def test_device_online_flag() -> None:
    """online keeps the raw bool; absence means "not reported", not offline.

    Only newer hardware/firmware sends the field; old firmware (e.g.
    Remo/1.0.69) omits it entirely, so None must stay distinct from False.
    """
    assert Device.from_dict({**DEVICE_PAYLOAD, "online": True}).online is True
    assert Device.from_dict({**DEVICE_PAYLOAD, "online": False}).online is False
    assert Device.from_dict(DEVICE_PAYLOAD).online is None


AIRCON_PAYLOAD = {
    "range": {
        "modes": {
            "cool": {
                "temp": ["24", "25", "26", "27", "28"],
                "vol": ["1", "2", "3", "auto"],
                "dir": ["1", "2", "swing", "auto"],
                "dirh": ["1", "2", "3", "swing"],
            },
            "dry": {"temp": [], "vol": ["auto"], "dir": [], "dirh": []},
            "auto": {
                "temp": ["-2", "-1", "0", "+1", "+2"],
                "vol": ["auto"],
                "dir": [],
                "dirh": [],
            },
        },
        "fixedButtons": ["power-off"],
    },
    "tempUnit": "c",
}


def test_aircon_from_dict() -> None:
    """Mode ranges, fixed buttons and temp unit parse."""
    aircon = Aircon.from_dict(AIRCON_PAYLOAD)

    assert set(aircon.modes) == {"cool", "dry", "auto"}
    assert aircon.modes["cool"].temperatures == ["24", "25", "26", "27", "28"]
    assert aircon.modes["cool"].directions_h == ["1", "2", "3", "swing"]
    assert aircon.modes["dry"].temperatures == []
    assert aircon.fixed_buttons == ["power-off"]
    assert aircon.temp_unit == "c"


def test_aircon_mode_range_drops_empty_string_entries() -> None:
    """The real API sends dirh: [""] as a "not supported" placeholder.

    Keeping the empty string would make directions_h non-empty and falsely
    enable horizontal swing; it must parse to an empty list instead.
    """
    mode_range = AirconModeRange.from_dict({"dirh": [""], "temp": ["1", ""]})

    assert mode_range.directions_h == []
    assert mode_range.temperatures == ["1"]


def test_aircon_settings_from_dict() -> None:
    """Settings parse, treating null-ish values as empty strings."""
    settings = AirconSettings.from_dict(
        {
            "temp": "26",
            "temp_unit": "c",
            "mode": "cool",
            "vol": "auto",
            "dir": "swing",
            "dirh": "",
            "button": None,
            "updated_at": "2026-07-18T06:00:00Z",
        }
    )

    assert settings.temperature == "26"
    assert settings.mode == "cool"
    assert settings.volume == "auto"
    assert settings.direction == "swing"
    assert settings.direction_h == ""
    assert settings.button == ""
    assert settings.updated_at is not None


def test_tv_from_dict() -> None:
    """TV buttons and input state parse."""
    tv = TV.from_dict(
        {
            "state": {"input": "t"},
            "buttons": [
                {"name": "power", "image": "ico_io", "label": "Power"},
                {"name": "vol-up", "image": "ico_vol_up", "label": "Volume up"},
            ],
        }
    )

    assert tv.state.input == "t"
    assert [b.name for b in tv.buttons] == ["power", "vol-up"]


def test_light_from_dict() -> None:
    """Light buttons and state parse; missing state fields become None."""
    light = Light.from_dict(
        {
            "state": {"brightness": "100", "power": "on", "last_button": "on"},
            "buttons": [{"name": "on", "image": "ico_on", "label": "On"}],
        }
    )

    assert light.state.power == "on"
    assert light.buttons[0].label == "On"

    empty = Light.from_dict({})
    assert empty.state.power is None
    assert empty.buttons == []


def test_signal_from_dict() -> None:
    """IR signals parse."""
    signal = Signal.from_dict({"id": "signal-1", "name": "Power", "image": "ico_io"})

    assert signal.id == "signal-1"
    assert signal.name == "Power"


def _meter(props: list[dict[str, object]]) -> SmartMeter:
    return SmartMeter.from_dict({"echonetlite_properties": props})


SMART_METER_PROPS: list[dict[str, object]] = [
    {
        "name": "coefficient",
        "epc": 211,
        "val": "1",
        "updated_at": "2026-07-18T07:00:00Z",
    },
    {
        "name": "cumulative_electric_energy_effective_digits",
        "epc": 215,
        "val": "6",
    },
    {
        "name": "normal_direction_cumulative_electric_energy",
        "epc": 224,
        "val": "123456",
    },
    {"name": "cumulative_electric_energy_unit", "epc": 225, "val": "1"},
    {
        "name": "reverse_direction_cumulative_electric_energy",
        "epc": 227,
        "val": "1234",
    },
    {"name": "measured_instantaneous", "epc": 231, "val": "520"},
]


def test_smart_meter_energy_math() -> None:
    """kWh = raw x coefficient x unit multiplier; power is raw watts."""
    meter = _meter(SMART_METER_PROPS)

    assert meter.instantaneous_power_w == 520
    assert meter.cumulative_energy_kwh == 12345.6
    assert meter.cumulative_energy_reverse_kwh == 123.4


def test_smart_meter_multiplying_unit_codes() -> None:
    """Unit codes 10-13 multiply (a naive 10^-n formula would be wrong)."""
    meter = _meter(
        [
            {"epc": 224, "val": "5", "name": "normal"},
            {"epc": 225, "val": "11", "name": "unit"},
        ]
    )

    assert meter.cumulative_energy_kwh == 500.0


def test_smart_meter_negative_power() -> None:
    """Instantaneous power is signed (negative = exporting)."""
    meter = _meter([{"epc": 231, "val": "-300", "name": "instant"}])

    assert meter.instantaneous_power_w == -300


def test_smart_meter_missing_unit_returns_none() -> None:
    """Without EPC 225 the cumulative energy cannot be scaled."""
    meter = _meter([{"epc": 224, "val": "123456", "name": "normal"}])

    assert meter.cumulative_energy_kwh is None
    assert meter.cumulative_energy_reverse_kwh is None
    assert meter.instantaneous_power_w is None


def test_smart_meter_coefficient_defaults_to_one() -> None:
    """Missing coefficient (EPC 211) defaults to 1."""
    meter = _meter(
        [
            {"epc": 224, "val": "100", "name": "normal"},
            {"epc": 225, "val": "2", "name": "unit"},
        ]
    )

    assert meter.cumulative_energy_kwh == 1.0


def test_appliance_from_dict_ac() -> None:
    """An AC appliance wires settings, aircon, model and device id."""
    appliance = Appliance.from_dict(
        {
            "id": "appliance-ac-1",
            "type": "AC",
            "nickname": "Living AC",
            "image": "ico_ac_1",
            "device": {"id": "device-1", "name": "Living Remo"},
            "model": {"id": "model-1", "manufacturer": "daikin", "name": "Daikin AC"},
            "settings": {"temp": "26", "mode": "cool", "vol": "auto", "button": ""},
            "aircon": AIRCON_PAYLOAD,
            "signals": [],
        }
    )

    assert appliance.type == "AC"
    assert appliance.device_id == "device-1"
    assert appliance.model is not None
    assert appliance.model.manufacturer == "daikin"
    assert appliance.settings is not None
    assert appliance.settings.mode == "cool"
    assert appliance.aircon is not None
    assert "cool" in appliance.aircon.modes
    assert appliance.tv is None
    assert appliance.smart_meter is None


def test_appliance_from_dict_ir_minimal() -> None:
    """An IR appliance has signals and no sub-objects."""
    appliance = Appliance.from_dict(
        {
            "id": "appliance-ir-1",
            "type": "IR",
            "nickname": "Fan",
            "signals": [{"id": "signal-1", "name": "Power", "image": "ico_io"}],
        }
    )

    assert appliance.device_id is None
    assert appliance.model is None
    assert [s.name for s in appliance.signals] == ["Power"]


DAIKIN_EXTRA_CATALOG = {
    "id": "autoclean",
    "text": "Mold Proof",
    "description": "Dries the inside after cool/dry operation.",
    "type": "choice",
    "options": [
        {"value": "off", "text": "Off", "default": True},
        {"value": "on", "text": "On"},
    ],
    "availability": "available",
}


def test_aircon_settings_extra_parsed() -> None:
    """settings.extra (remote-side state such as autoclean) is preserved."""
    settings = AirconSettings.from_dict(
        {"temp": "26", "mode": "cool", "extra": {"autoclean": "on"}}
    )

    assert settings.extra == {"autoclean": "on"}

    empty = AirconSettings.from_dict({"temp": "26", "mode": "cool"})
    assert empty.extra == {}


def test_aircon_extras_catalog_parsed() -> None:
    """range.extras enumerates device-specific parameters with options."""
    aircon = Aircon.from_dict(
        {
            "range": {
                "modes": {},
                "fixedButtons": [],
                "extras": [DAIKIN_EXTRA_CATALOG],
            },
            "tempUnit": "c",
        }
    )

    assert len(aircon.extras) == 1
    extra = aircon.extras[0]
    assert extra.id == "autoclean"
    assert extra.availability == "available"
    assert [(o.value, o.default) for o in extra.options] == [
        ("off", True),
        ("on", False),
    ]

    no_extras = Aircon.from_dict({"range": {"modes": {}, "fixedButtons": []}})
    assert no_extras.extras == []


def test_aircon_extra_time_type_default_time() -> None:
    """Time-type extras (e.g. Daikin new_sleep) carry defaultTime, no options."""
    extra = AirconExtra.from_dict(
        {
            "id": "new_sleep",
            "text": "Night Set Mode",
            "description": "Raises then lowers the set temperature overnight.",
            "type": "time",
            "defaultTime": "21:00",
            "availability": "hidden",
        }
    )

    assert extra.type == "time"
    assert extra.default_time == "21:00"
    assert extra.options == []
    assert extra.availability == "hidden"

    choice = AirconExtra.from_dict(DAIKIN_EXTRA_CATALOG)
    assert choice.default_time is None


def test_appliance_model_country_and_slug() -> None:
    """country and slug parse when present and default to None."""
    model = ApplianceModel.from_dict(
        {
            "id": "model-sesame-1",
            "manufacturer": "CANDY HOUSE",
            "country": "JP",
            "slug": "sesame5",
        }
    )

    assert model.country == "JP"
    assert model.slug == "sesame5"

    bare = ApplianceModel.from_dict({"id": "model-1"})
    assert bare.country is None
    assert bare.slug is None


FLOOR_HEATER_PAYLOAD = {
    "range": {
        "modes": {
            "auto": {
                "temp": ["-2", "-1", "0", "1", "2"],
                "dir": [""],
                "dirh": [""],
                "vol": [""],
            },
            "warm": {
                "temp": [
                    "17",
                    "18",
                    "19",
                    "20",
                    "21",
                    "22",
                    "23",
                    "24",
                    "25",
                    "26",
                    "27",
                    "28",
                    "29",
                    "30",
                ],
                "dir": [""],
                "dirh": [""],
                "vol": [""],
            },
        },
        "fixedButtons": ["power-off"],
        "extras": [
            {
                "id": "save_energy",
                "text": "Save energy",
                "description": "Reduce heating power",
                "type": "choice",
                "options": [
                    {"value": "off", "text": "Off", "default": True},
                    {"value": "on", "text": "On"},
                ],
                "availability": "available",
            }
        ],
    },
    "tempUnit": "c",
}


def test_floor_heater_from_dict() -> None:
    """The floor_heater capability parses with the aircon shape."""
    heater = FloorHeater.from_dict(FLOOR_HEATER_PAYLOAD)

    assert type(heater) is FloorHeater
    assert set(heater.modes) == {"auto", "warm"}
    assert heater.modes["auto"].temperatures == ["-2", "-1", "0", "1", "2"]
    assert heater.modes["warm"].temperatures[0] == "17"
    assert heater.modes["warm"].temperatures[-1] == "30"
    assert heater.modes["warm"].volumes == []
    assert heater.modes["warm"].directions == []
    assert heater.fixed_buttons == ["power-off"]
    assert heater.temp_unit == "c"
    assert [extra.id for extra in heater.extras] == ["save_energy"]
    assert [(o.value, o.default) for o in heater.extras[0].options] == [
        ("off", True),
        ("on", False),
    ]


def test_appliance_from_dict_floor_heater() -> None:
    """A FLOOR_HEATER appliance parses settings and the capability object."""
    appliance = Appliance.from_dict(
        {
            "id": "appliance-fh-1",
            "type": "FLOOR_HEATER",
            "nickname": "Floor heater",
            "image": "ico_floor_heater",
            "device": {"id": "device-2", "name": "Bedroom Remo mini"},
            "model": {
                "id": "model-fh-1",
                "country": "JP",
                "manufacturer": "Corona",
                "remote_name": "rfc-a04",
                "series": "",
                "name": "Corona Floor Heater 001",
                "image": "ico_floor_heater",
            },
            "settings": {
                "temp": "0",
                "temp_unit": "c",
                "mode": "auto",
                "vol": "",
                "dir": "",
                "dirh": "",
                "button": "power-off",
                "updated_at": "2026-07-25T00:06:51Z",
                "extra": {"save_energy": "off"},
            },
            "aircon": None,
            "signals": [],
            "floor_heater": FLOOR_HEATER_PAYLOAD,
        }
    )

    assert appliance.type == "FLOOR_HEATER"
    assert appliance.aircon is None
    assert appliance.settings is not None
    assert appliance.settings.mode == "auto"
    assert appliance.settings.button == "power-off"
    assert appliance.settings.extra == {"save_energy": "off"}
    assert appliance.floor_heater is not None
    assert type(appliance.floor_heater) is FloorHeater
    assert "warm" in appliance.floor_heater.modes


def _layout_button(name: str, text: str) -> dict[str, object]:
    """Build a layout button leaf with the real API field shape."""
    return {
        "type": "button",
        "name": name,
        "uuid": f"uuid-{name}",
        "image": f"ico_{name.replace('-', '_')}",
        "label": "",
        "text": text,
        "x_size": 1,
        "y_size": 1,
    }


# Mirrors the real Anker Nebula Nova layout tree: composite nodes
# (plus_minus_buttons_1 / control_buttons_1) nest their leaves one level
# deeper under "templates".
LIGHT_PROJECTOR_PAYLOAD = {
    "layout": {
        "type": "root",
        "name": "root",
        "uuid": "",
        "image": "",
        "label": "",
        "text": "",
        "x_size": 4,
        "y_size": 0,
        "templates": [
            {
                "type": "template",
                "name": "template-1",
                "uuid": "uuid-template-1",
                "label": "",
                "x_size": 4,
                "y_size": 2,
                "templates": [
                    {
                        "type": "plus_minus_buttons_1",
                        "name": "plus-minus-1",
                        "uuid": "uuid-plus-minus-1",
                        "label": "",
                        "x_size": 1,
                        "y_size": 2,
                        "templates": [
                            _layout_button("plus", "Volume Up"),
                            _layout_button("minus", "Volume Down"),
                        ],
                    },
                    {
                        "type": "control_buttons_1",
                        "name": "control-1",
                        "uuid": "uuid-control-1",
                        "label": "",
                        "x_size": 2,
                        "y_size": 2,
                        "templates": [
                            _layout_button("arrow-top", "Top"),
                            _layout_button("arrow-left", "Left"),
                            _layout_button("record", "Ok"),
                            _layout_button("arrow-right", "Right"),
                            _layout_button("arrow-bottom", "Bottom"),
                        ],
                    },
                    _layout_button("light-all", "Light"),
                    _layout_button("focus", "Auto Forcus"),
                ],
            },
            _layout_button("io", "Power"),
            _layout_button("home", "Home"),
            _layout_button("return", "Back"),
            _layout_button("setting", "Settings"),
        ],
    }
}


def test_appliance_from_dict_light_projector() -> None:
    """A LIGHT_PROJECTOR appliance flattens its layout in document order."""
    appliance = Appliance.from_dict(
        {
            "id": "appliance-projector-1",
            "type": "LIGHT_PROJECTOR",
            "nickname": "Projector",
            "image": "ico_light_projector",
            "device": {"id": "device-2", "name": "Bedroom Remo mini"},
            "model": {
                "id": "model-projector-1",
                "country": "JP",
                "manufacturer": "Anker Japan",
                "remote_name": "Nebula Nova",
                "name": "Nebula Nova",
                "image": "ico_projector",
            },
            "settings": None,
            "aircon": None,
            "signals": [],
            "light_projector": LIGHT_PROJECTOR_PAYLOAD,
        }
    )

    assert appliance.settings is None
    assert appliance.aircon is None
    assert appliance.floor_heater is None
    assert appliance.light_projector is not None
    assert [b.name for b in appliance.light_projector.buttons] == [
        "plus",
        "minus",
        "arrow-top",
        "arrow-left",
        "record",
        "arrow-right",
        "arrow-bottom",
        "light-all",
        "focus",
        "io",
        "home",
        "return",
        "setting",
    ]
    plus = appliance.light_projector.buttons[0]
    assert plus.text == "Volume Up"
    assert plus.uuid == "uuid-plus"
    assert plus.image == "ico_plus"


def test_light_projector_skips_unnamed_buttons() -> None:
    """Button leaves with an empty name are dropped (cannot be sent)."""
    projector = LightProjector.from_dict(
        {
            "layout": {
                "type": "root",
                "name": "root",
                "templates": [
                    {"type": "button", "name": "", "text": "Ghost"},
                    {"type": "button", "name": "io", "text": "Power"},
                ],
            }
        }
    )

    assert [b.name for b in projector.buttons] == ["io"]

    empty = LightProjector.from_dict({})
    assert empty.buttons == []


def test_echonetlite_appliance_from_dict() -> None:
    """Parses the Remo E API shape: hex EPC strings and a capital-D Device key."""
    appliance = EchonetLiteAppliance.from_dict(
        {
            "id": "el-appliance-1",
            "nickname": "スマートメーター",
            "type": "EL_SMART_METER",
            "properties": [
                {"epc": "e7", "val": "000004ed", "updated_at": "2026-07-29T07:54:09Z"},
                {"epc": "8a", "val": "000016", "updated_at": "2026-07-29T07:55:20Z"},
            ],
            "Device": {
                "id": "device-elite-1",
                "name": "Remo E lite",
                "firmware_version": "Remo-E-lite/1.12.0",
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "serial_number": "4W0000000000000",
                "temperature_offset": 0,
                "humidity_offset": 0,
            },
        }
    )

    assert appliance.id == "el-appliance-1"
    assert appliance.nickname == "スマートメーター"
    assert appliance.type == "EL_SMART_METER"
    assert [prop.epc for prop in appliance.properties] == ["e7", "8a"]
    assert appliance.properties[0].val == "000004ed"
    assert appliance.properties[0].updated_at == datetime(
        2026, 7, 29, 7, 54, 9, tzinfo=UTC
    )
    assert appliance.device is not None
    assert appliance.device.name == "Remo E lite"
    assert appliance.device.online is None  # endpoint omits the online field


def test_echonetlite_appliance_tolerates_missing_fields() -> None:
    """No Device key, absent updated_at, and junk property entries survive."""
    appliance = EchonetLiteAppliance.from_dict(
        {
            "id": "el-appliance-2",
            "properties": [
                {"epc": "d3", "val": "00000001"},
                "junk",
                {"val": "no-epc"},
            ],
        }
    )

    assert appliance.nickname == ""
    assert appliance.type == ""
    assert appliance.device is None
    assert [prop.epc for prop in appliance.properties] == ["d3"]
    assert appliance.properties[0].updated_at is None
