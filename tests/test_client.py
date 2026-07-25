"""Tests for the NatureRemoClient transport layer.

The client talks to a real local aiohttp server (aiohttp's own test
utilities) instead of a request-mocking library, so these tests stay valid
for every aiohttp version the package supports.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aionatureremo import (
    NatureRemoApiError,
    NatureRemoAuthError,
    NatureRemoClient,
    NatureRemoConnectionError,
    NatureRemoRateLimitError,
    User,
)


@dataclass
class RecordedRequest:
    """One request received by the fake API."""

    method: str
    path: str
    headers: dict[str, str]
    data: dict[str, str]


@dataclass
class _ResponseSpec:
    status: int
    payload: Any
    body: str | None
    headers: dict[str, str]


class FakeNatureApi:
    """Programmable stand-in for api.nature.global."""

    def __init__(self) -> None:
        self.base_url = ""
        self.requests: list[RecordedRequest] = []
        self._responses: dict[tuple[str, str], _ResponseSpec] = {}

    def respond(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        payload: Any = None,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Configure the response for a method + path."""
        self._responses[(method, path)] = _ResponseSpec(
            status=status, payload=payload, body=body, headers=headers or {}
        )

    async def handle(self, request: web.Request) -> web.Response:
        """Record the request and serve the configured response."""
        self.requests.append(
            RecordedRequest(
                method=request.method,
                path=request.path,
                headers=dict(request.headers),
                data=dict(await request.post()),
            )
        )
        spec = self._responses.get((request.method, request.path))
        if spec is None:
            return web.Response(status=404, text="unexpected request")
        if spec.payload is not None:
            return web.json_response(
                spec.payload, status=spec.status, headers=spec.headers
            )
        return web.Response(
            status=spec.status, text=spec.body or "", headers=spec.headers
        )


@pytest.fixture
async def fake_api() -> AsyncGenerator[FakeNatureApi]:
    """Serve a programmable fake Nature API on a local port."""
    api = FakeNatureApi()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", api.handle)
    server = TestServer(app)
    await server.start_server()
    api.base_url = str(server.make_url("/"))
    yield api
    await server.close()


@pytest.fixture
async def session() -> AsyncGenerator[aiohttp.ClientSession]:
    """Provide a real aiohttp session."""
    session = aiohttp.ClientSession()
    yield session
    await session.close()


@pytest.fixture
def client(session: aiohttp.ClientSession, fake_api: FakeNatureApi) -> NatureRemoClient:
    """Provide a client under test wired to the fake API."""
    return NatureRemoClient("test-token", session, base_url=fake_api.base_url)


async def test_get_user(client: NatureRemoClient, fake_api: FakeNatureApi) -> None:
    """A successful GET parses the user and sends the bearer token."""
    fake_api.respond(
        "GET", "/1/users/me", payload={"id": "user-1", "nickname": "Alice"}
    )

    user = await client.get_user()

    assert user == User(id="user-1", nickname="Alice")
    assert fake_api.requests[0].headers["Authorization"] == "Bearer test-token"


async def test_rate_limit_headers_tracked(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """X-Rate-Limit headers update client.rate_limit."""
    fake_api.respond(
        "GET",
        "/1/users/me",
        payload={"id": "user-1", "nickname": "Alice"},
        headers={
            "X-Rate-Limit-Limit": "30",
            "X-Rate-Limit-Remaining": "29",
            "X-Rate-Limit-Reset": "1752825600",
        },
    )

    await client.get_user()

    assert client.rate_limit.limit == 30
    assert client.rate_limit.remaining == 29
    assert client.rate_limit.reset == 1752825600


async def test_unauthorized_raises_auth_error(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """HTTP 401 raises NatureRemoAuthError."""
    fake_api.respond("GET", "/1/users/me", status=401)

    with pytest.raises(NatureRemoAuthError) as err:
        await client.get_user()
    assert err.value.status == 401


async def test_rate_limited_raises_with_reset(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """HTTP 429 raises NatureRemoRateLimitError carrying the reset epoch."""
    fake_api.respond(
        "GET",
        "/1/users/me",
        status=429,
        headers={"X-Rate-Limit-Reset": "1752825600"},
    )

    with pytest.raises(NatureRemoRateLimitError) as err:
        await client.get_user()
    assert err.value.reset == 1752825600


async def test_server_error_raises_api_error(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """HTTP 5xx raises NatureRemoApiError with the status."""
    fake_api.respond("GET", "/1/users/me", status=500, body="boom")

    with pytest.raises(NatureRemoApiError) as err:
        await client.get_user()
    assert err.value.status == 500
    assert isinstance(err.value, NatureRemoApiError)
    assert not isinstance(err.value, NatureRemoAuthError)


async def test_network_failure_raises_connection_error(
    session: aiohttp.ClientSession,
) -> None:
    """aiohttp errors surface as NatureRemoConnectionError."""
    client = NatureRemoClient("test-token", session, base_url="http://127.0.0.1:1")

    with pytest.raises(NatureRemoConnectionError):
        await client.get_user()


async def test_get_devices(client: NatureRemoClient, fake_api: FakeNatureApi) -> None:
    """Devices endpoint parses into a list of Device."""
    fake_api.respond(
        "GET",
        "/1/devices",
        payload=[
            {
                "id": "device-1",
                "name": "Living Remo",
                "firmware_version": "Remo/1.14.8",
                "newest_events": {
                    "te": {"val": 26.4, "created_at": "2026-07-18T07:59:00Z"}
                },
            }
        ],
    )

    devices = await client.get_devices()

    assert len(devices) == 1
    assert devices[0].id == "device-1"
    assert devices[0].events["te"].value == 26.4


async def test_set_temperature_offset(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Offset update POSTs a form body and returns the updated device."""
    fake_api.respond(
        "POST",
        "/1/devices/device-1/temperature_offset",
        payload={"id": "device-1", "name": "Living Remo", "temperature_offset": 2},
    )

    device = await client.set_temperature_offset("device-1", 2)

    assert device.temperature_offset == 2.0
    assert fake_api.requests[0].data == {"offset": "2"}


async def test_set_humidity_offset(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Humidity offset hits its own endpoint."""
    fake_api.respond(
        "POST",
        "/1/devices/device-1/humidity_offset",
        payload={"id": "device-1", "name": "Living Remo", "humidity_offset": -3},
    )

    device = await client.set_humidity_offset("device-1", -3)

    assert device.humidity_offset == -3.0


async def test_get_appliances(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Appliances endpoint parses into typed Appliance objects."""
    fake_api.respond(
        "GET",
        "/1/appliances",
        payload=[
            {
                "id": "appliance-tv-1",
                "type": "TV",
                "nickname": "Living TV",
                "device": {"id": "device-1"},
                "tv": {"state": {"input": "t"}, "buttons": [{"name": "power"}]},
            }
        ],
    )

    appliances = await client.get_appliances()

    assert appliances[0].type == "TV"
    assert appliances[0].tv is not None
    assert appliances[0].tv.state.input == "t"


async def test_set_aircon_settings(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Only provided kwargs are form-encoded; empty strings are kept."""
    fake_api.respond(
        "POST",
        "/1/appliances/appliance-ac-1/aircon_settings",
        payload={"temp": "27", "mode": "cool", "vol": "auto", "button": ""},
    )

    settings = await client.set_aircon_settings(
        "appliance-ac-1",
        operation_mode="cool",
        temperature="27",
        air_volume="auto",
        button="",
    )

    assert settings.temperature == "27"
    assert fake_api.requests[0].data == {
        "operation_mode": "cool",
        "temperature": "27",
        "air_volume": "auto",
        "button": "",
    }


# Mirrors the real floor_heater_settings response: the WHOLE Appliance
# object, unlike aircon_settings which returns bare settings.
FLOOR_HEATER_APPLIANCE_RESPONSE = {
    "id": "appliance-fh-1",
    "type": "FLOOR_HEATER",
    "nickname": "Floor heater",
    "image": "ico_floor_heater",
    "device": {"id": "device-2", "name": "Bedroom Remo mini"},
    "model": {"id": "model-fh-1", "country": "JP", "manufacturer": "Corona"},
    "settings": {
        "temp": "20",
        "temp_unit": "c",
        "mode": "warm",
        "vol": "",
        "dir": "",
        "dirh": "",
        "button": "",
        "updated_at": "2026-07-25T02:40:44Z",
        "extra": {"save_energy": "off"},
    },
    "aircon": None,
    "signals": [],
    "floor_heater": {
        "range": {
            "modes": {
                "warm": {
                    "temp": ["17", "18", "19", "20"],
                    "dir": [""],
                    "dirh": [""],
                    "vol": [""],
                }
            },
            "fixedButtons": ["power-off"],
            "extras": [],
        },
        "tempUnit": "c",
    },
}


async def test_set_floor_heater_settings(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """floor_heater_settings POSTs a form and parses the whole appliance."""
    fake_api.respond(
        "POST",
        "/1/appliances/appliance-fh-1/floor_heater_settings",
        payload=FLOOR_HEATER_APPLIANCE_RESPONSE,
    )

    appliance = await client.set_floor_heater_settings(
        "appliance-fh-1",
        operation_mode="warm",
        temperature="20",
        extra={"save_energy": "off"},
    )

    assert fake_api.requests[0].data == {
        "operation_mode": "warm",
        "temperature": "20",
        "extra.save_energy": "off",
    }
    assert appliance.id == "appliance-fh-1"
    assert appliance.settings is not None
    assert appliance.settings.mode == "warm"
    assert appliance.settings.temperature == "20"
    assert appliance.settings.extra == {"save_energy": "off"}
    assert appliance.aircon is None
    assert appliance.floor_heater is not None
    assert appliance.floor_heater.fixed_buttons == ["power-off"]


async def test_set_floor_heater_settings_empty_body(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """A degenerate empty 200 body raises a typed error, not a KeyError."""
    fake_api.respond(
        "POST", "/1/appliances/appliance-fh-1/floor_heater_settings", body=""
    )

    with pytest.raises(NatureRemoApiError):
        await client.set_floor_heater_settings("appliance-fh-1", button="power-off")


async def test_send_light_projector_button(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Projector button POSTs the form and tolerates the empty {} body."""
    fake_api.respond(
        "POST", "/1/appliances/appliance-projector-1/light_projector", payload={}
    )

    result = await client.send_light_projector_button("appliance-projector-1", "minus")

    assert result is None
    assert fake_api.requests[0].data == {"button": "minus"}


async def test_send_tv_button(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """TV button POST returns the new TV state."""
    fake_api.respond("POST", "/1/appliances/appliance-tv-1/tv", payload={"input": "bs"})

    state = await client.send_tv_button("appliance-tv-1", "bs")

    assert state.input == "bs"
    assert fake_api.requests[0].data == {"button": "bs"}


async def test_send_light_button(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """Light button POST returns the new light state."""
    fake_api.respond(
        "POST",
        "/1/appliances/appliance-light-1/light",
        payload={"power": "off", "brightness": "100", "last_button": "off"},
    )

    state = await client.send_light_button("appliance-light-1", "off")

    assert state.power == "off"


async def test_send_signal(client: NatureRemoClient, fake_api: FakeNatureApi) -> None:
    """Signal send POSTs an empty body and returns None."""
    fake_api.respond("POST", "/1/signals/signal-1/send", body="")

    assert await client.send_signal("signal-1") is None


async def test_set_aircon_settings_serializes_extra(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """extra entries become dotted extra.$id form fields."""
    fake_api.respond(
        "POST",
        "/1/appliances/appliance-ac-1/aircon_settings",
        payload={"temp": "26", "mode": "cool", "extra": {"autoclean": "on"}},
    )

    settings = await client.set_aircon_settings(
        "appliance-ac-1",
        operation_mode="cool",
        button="",
        extra={"autoclean": "on"},
    )

    assert settings.extra == {"autoclean": "on"}
    assert fake_api.requests[0].data == {
        "operation_mode": "cool",
        "button": "",
        "extra.autoclean": "on",
    }
