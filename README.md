# aionatureremo

Asynchronous Python client for the [Nature Remo Cloud API](https://developer.nature.global/).

Built for Home Assistant: aiohttp session injection, fully typed, no dependencies beyond aiohttp.

## Usage

```python
import aiohttp
from aionatureremo import NatureRemoClient

async with aiohttp.ClientSession() as session:
    client = NatureRemoClient("YOUR_ACCESS_TOKEN", session)
    devices = await client.get_devices()
```

Get an access token at https://home.nature.global/.

The Nature Remo E API (`/1/echonetlite/appliances` — smart meters and,
per Nature's docs, storage batteries / solar / EV chargers / water
heaters) is exposed via `get_echonetlite_appliances()` and
`request_echonetlite_refresh(appliance_id, epcs)`. EPC values pass
through as raw lowercase-hex strings; `POST …/set` (a paid Nature
option) is deliberately not implemented.
