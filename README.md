[![](https://img.shields.io/github/release/danalec/ha-samsungtv/all.svg?style=for-the-badge)](https://github.com/danalec/ha-samsungtv/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![](https://img.shields.io/github/license/danalec/ha-samsungtv?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/badge/MAINTAINER-%40danalec-red?style=for-the-badge)](https://github.com/danalec)
[![](https://img.shields.io/badge/COMMUNITY-FORUM-success?style=for-the-badge)](https://community.home-assistant.io)

# Home Assistant - SamsungTV Custom Component

A custom component that controls Samsung TVs from [Home Assistant](https://home-assistant.io).

This integration is **the official [`samsungtv` integration](https://www.home-assistant.io/integrations/samsungtv/)**, taken
from `home-assistant/core`, adapted to the `samsungtv_custom` domain, plus **key chaining**.

## Why this fork exists

The official integration ships with Home Assistant. This fork exists for the features it does not have:

- **Chained keys** — send a sequence of keys with explicit delays between them, so a TV actually follows a menu instead of
  dropping the keys you sent too fast.
- **A `send_key` media type** — send any raw Samsung key code through the stock `media_player.play_media` service, without
  a custom service to register.

Everything else deliberately tracks upstream. The protocol layer (`bridge.py`) is byte-for-byte identical to the official
integration, so a bug fixed upstream lands here without a rewrite.

## What you get

Two entities per TV:

| Entity | Platform | Notes |
| --- | --- | --- |
| `media_player.<name>` | `media_player` | Device class `TV`: power, volume, mute, transport controls, source selection |
| `remote.<name>` | `remote` | Sends raw key commands, with repeat support |

Plus:

- **Three protocols**, chosen automatically per model — see [Protocols](#protocols).
- **2021+ TV support** via the encrypted websocket on port 8000, with PIN pairing.
- **Discovery** over DHCP, SSDP and zeroconf (AirPlay), so the TV shows up in the UI without typing an IP address.
- **Volume and mute over UPnP** (`RenderingControl`), which needs discovery — without it, those two features degrade.
- **Device triggers** for turn on and turn off, so automations can act on TV state.
- **App list** read from the TV, merged into the `media_player` source list — see [apps and app IDs](docs/App_ids.md).

## Requirements

| | |
| --- | --- |
| Home Assistant | **2026.10.0** or newer |
| Python | **3.14.2** or newer |
| TV | 2016 or newer (Tizen family) |

The Python floor is not a preference. The bridge inherited from upstream uses PEP 649 lazy annotations and PEP 758
unparenthesized `except` clauses, and neither parses before 3.14.

Your TV and Home Assistant must be on the same network. Samsung TVs do not accept websocket connections across VLANs.

## Installation

### HACS

Add this repository as a custom repository of type *Integration*, install **SamsungTV Custom**, and restart Home Assistant.

### Manual

Copy `custom_components/samsungtv_custom/` into the `custom_components/` directory of your Home Assistant configuration
directory, creating it if it does not exist, then restart Home Assistant.

## Configuration

Configuration is UI-only — there is no `configuration.yaml` block for this integration.

1. Go to **Settings** → **Devices & services** → **Add integration**.
2. If your TV was discovered, it is listed automatically; otherwise search for **SamsungTV** and enter the host and name.
3. Confirm. If you have never connected Home Assistant to this TV, a popup appears **on the TV** — accept it within
   30 seconds.
4. For a 2021 or newer TV, the TV displays a PIN. Enter it in the dialog.

If setup fails, power cycle the TV first. Applications left running on the TV can hold the websocket port and block the
connection. Check the Home Assistant log for the reason.

The integration supports **re-authentication** (when the TV revokes authorization) and **reconfigure** (when the TV's IP
address changes), both from the integration's overflow menu.

## How state is updated

Power state is **polled every 10 seconds** (`SCAN_INTERVAL` in `coordinator.py`). That is the only periodic traffic this
integration generates, and it continues for as long as the entry is loaded. What that poll costs depends on the protocol:

| Protocol | How power state is read |
| --- | --- |
| `legacy` (55000) | One blocking `samsungctl` ping, run in an executor |
| `websocket` (8001/8002) | `is_alive()` on the connection that is already open — no extra request |
| `encrypted` (8000) | A REST device-info call for `PowerState`, refreshed on every poll |

The encrypted bridge deliberately avoids its fallback path: when a model does not report `PowerState` in its device
info, opening a websocket can **wake the TV**. If your 2021+ TV turns itself on after a while with this integration
loaded, that is the path being taken.

Volume and mute are **not** polled. They arrive as UPnP `RenderingControl` events from the TV, which is what
`iot_class: local_push` refers to. Without discovery there is no UPnP device, those two attributes stop updating, and
the volume slider stops working while volume up/down and mute still do — those send key codes.

Two behaviours worth knowing:

- After a power-off key is sent, the bridge refuses further commands until the TV has settled, so a stray key cannot turn
  it straight back on.
- If the TV revokes authorization, polling stops and Home Assistant starts the **re-authentication** flow. The entities
  go unavailable until you accept the prompt on the TV or enter the PIN.

## Protocols

The bridge picks one method per model and falls back only where the model allows it.

| Method | Port | TVs |
| --- | --- | --- |
| `legacy` | 55000 | Older Tizen models, no API |
| `websocket` | 8001 / 8002 | **Most 2016+ TVs, including every Neo QLED** |
| `encrypted` | 8000 | **H and J series only** (the 2021 naming) |

Selection is by model name: the letter in position 5 of the model string decides. `UN55HU6900` has an H there, so it
needs the PIN flow; `QN90B` has a B there, so it does not. When the encrypted method is tried and the TV refuses to
connect, the integration falls back to websocket on its own.

If a 2021+ TV settles on `legacy`, the model was not detected correctly and the TV will refuse keys. Open an issue with
the log.

## Validated models

Checked against real hardware, or against a protocol trace captured from it:

| Model | Protocol | Notes |
| --- | --- | --- |
| `QN90B` (Neo QLED 90", 2022) | websocket, **8002 only** | Plain `ws://` on 8001 is refused by this firmware. Pairing asks for no PIN — the TV grants the token silently on the `Allow` popup, or with no popup at all once the client name is authorized |
| `Q80B` / `QN80B` (Neo QLED 80", 2022) | websocket, **8002 only** | Same firmware family as the QN90B: same pairing, same refusal of 8001 |
| `QN900B`, `QN85B`, `QN90C/D/E` | websocket | Later Neo QLED generations; the year letter sits in the same position and does not change the transport |
| `UN55HU6900`, `UE55JU6800` (H/J series) | encrypted, 8000 | PIN pairing, part of setup |

Two behaviours specific to this family are worth calling out:

- **Instant On changes what "off" means.** With *Settings → General & Privacy → Power and Energy Saving → Instant On*
  enabled, the TV keeps its network alive in standby. Power state then reads as on while the screen is black, and the
  entity reports the TV as on. Turn Instant On off for a true deep-off state.
- **Rejections are quiet.** When the TV refuses the stored token it answers the command with
  `ms.error {"message": "No Authorized"}` and keeps the socket open rather than closing it. An integration that only
  inspects connect-time errors sits there looking healthy while dropping every key. This one notices and starts
  re-authentication — see [scripts/verify_protocol.py](scripts/verify_protocol.py).

Neo QLEDs from 2026 (`QN90H` and siblings) put an **H** in position 5, which the 2021 H-series rule reads as "needs
encrypted". The encrypted attempt fails on them and the integration falls back to websocket, so they do work — but the
entry is created as `encrypted` first and the log will say so.

## Usage

### Raw keys

`media_player.play_media` with `media_content_type: send_key`:

```yaml
service: media_player.play_media
data:
  entity_id: media_player.samsung_tv
  media_content_type: send_key
  media_content_id: KEY_HOME
```

See [the key code list](docs/Key_codes.md).

### Key chaining

Join keys with `+` to send a sequence. A numeric segment is an explicit delay in milliseconds, clamped to 200–2000 ms.
Consecutive keys are separated by a default 500 ms, because a TV that receives two keys at once drops one of them.

```yaml
service: media_player.play_media
data:
  entity_id: media_player.samsung_tv
  media_content_type: send_key
  media_content_id: KEY_SOURCES+500+KEY_ENTER
```

The example above opens the source menu. See [the chaining patterns](docs/Key_chaining.md).

### Channels

```yaml
service: media_player.play_media
data:
  entity_id: media_player.samsung_tv
  media_content_type: channel
  media_content_id: "14"
```

### Apps

```yaml
service: media_player.play_media
data:
  entity_id: media_player.samsung_tv
  media_content_type: app
  media_content_id: "11101200001"
```

### Remote

```yaml
service: remote.send_command
target:
  entity_id: remote.samsung_tv
data:
  command:
    - KEY_HOME
    - KEY_EXIT
  num_repeats: 1
```

### Turning the TV on

`media_player.turn_on` sends a **wake-on-LAN** packet when the MAC address known to Home Assistant is usable. Samsung TVs
are commonly documented as ignoring those, and that holds for many of them — but it does not hold for the Neo QLED
family, where a magic packet wakes the TV from deep standby.

If a **turn on automation** is attached to the TV in **Settings** → **Automations & Scenes** → **Device triggers** →
**Device is requested to turn on**, that automation runs too, after the packet. That is how an HDMI-CEC capable device, a
Raspberry Pi, or another hub joins in — the automation covers what wake-on-LAN cannot.

With neither a usable MAC nor an automation, `turn_on` raises an error saying exactly that, instead of silently doing
nothing.

Samsung TVs have a **different MAC per interface**. The address used here is the one the TV reported during setup, which
is its Wi-Fi address. If your TV is on Ethernet, or if `turn_on` does nothing, that is the first thing to check.

### Sources

The source list is built from the TV itself. While it is on, the integration asks which physical inputs exist and lists
them alongside the apps:

```
TV · HDMI 1 · HDMI 2 · Terrestrial · Netflix · Spotify
```

Selecting `HDMI 2` switches to it exactly, using the identifier the TV reported. That is firmware-dependent — some
firmware ignores the request — and when the TV does not answer, the list keeps the generic `TV` and `HDMI` entries, which
switch by key code as they always did.

The list is fetched once, when the TV is on at startup, so an input plugged in later appears after Home Assistant
reloads the integration.

## Not included

These came from the lineage this fork was originally based on and are **not** in this component. They are listed so nobody
goes looking for them:

- **SmartThings cloud API** — channel names, HDMI source detection, `ST_*` keys. No token is requested, and nothing leaves
  your network.
- **Channel and app logos**, `entity_picture`.
- **Picture mode, sound mode and art mode** services.
- **Custom services.** The integration registers none; it uses the standard `media_player` and `remote` services.
- **YAML configuration and options** — the source list is built from the TV (`TV`, `HDMI`, plus the apps the TV reports),
  not configured by hand.
- **Hold keys** (`KEY_CODE, <hold_time>`). Use `num_repeats` on `remote.send_command` instead.

Inherited from upstream, and worth knowing before you build on top of it:

- **The active source is never reported.** `media_player.select_source` works, and the source list is correct, but the
  entity does not expose which source the TV is on. The same applies to the running app.
- **The app list is fetched once at startup**, and never on the `legacy` protocol. See [apps and app IDs](docs/App_ids.md).

## Development

There is no build step and no lockfile. The component is plain Python; dependencies are declared in `manifest.json` and
installed by Home Assistant.

```bash
python -m compileall -q custom_components/samsungtv_custom   # byte-compile
ruff check custom_components/samsungtv_custom               # lint (ruff.toml)
python scripts/verify_keychain.py                           # key chain parsing, delay clamping
python scripts/verify_imports.py                            # no orphaned or broken relative imports
python scripts/verify_strings.py                            # strings.json and translations agree leaf for leaf
python scripts/verify_repo.py                               # no .pyc tracked, every tracked file ends with a newline
python scripts/verify_protocol.py                           # model -> protocol routing and token-rejection handling
python scripts/verify_power.py                              # wake-on-lan, MAC validation and the turn_on decision
python scripts/verify_sources.py                            # direct source switching, both reply shapes and the fallback
```

`ruff.toml` requires ruff **0.16.10** or newer, the same floor as upstream. To run it without installing anything:

```bash
uvx ruff@0.16.10 check custom_components/samsungtv_custom
```

Home Assistant is not a dev dependency, so the verification scripts read the real shipped files rather than a copy: the
key-chain and import checks extract the functions they exercise with `ast`, and the strings check compares
`strings.json` against every file in `translations/` leaf for leaf.

Both commands run in CI on every push and pull request (`.github/workflows/verify.yaml`), alongside
`home-assistant/actions/hassfest` for manifest and `strings.json` validation (`.github/workflows/hassfest.yaml`).

Protocol fixes belong upstream in `home-assistant/core`. See [AGENTS.md](AGENTS.md) for the full contributor guide.

## Removing the integration

Delete it from **Settings** → **Devices & services** → the integration's overflow menu → **Delete**. Nothing is left behind:
no token file, no cloud account, no state outside Home Assistant.

Then revoke access on the TV itself, otherwise it keeps listing Home Assistant as an authorized device:
**Settings** → **General** → **External Device Manager**. On some firmware versions this screen only appears while the TV
is on and not in a menu.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Setup hangs, no popup on the TV | The TV is powered off or a running application is holding the websocket. Power cycle it |
| "not authorized to connect" | Reject the TV's **External Device Manager** prompt, then reconfigure the integration |
| Keys do nothing and nothing is logged | The TV refused the token. Re-authentication is now started; accept the prompt on the TV |
| Keys do nothing on a 2021 H/J TV | The entry settled on `legacy` instead of `encrypted` — the model was not detected |
| Log shows 8001 failing on a Neo QLED | That firmware refuses plain `ws://`. The integration retries on 8002 automatically |
| TV shows `on` while the screen is black | **Instant On** is enabled, keeping the network alive in standby. Turn it off |
| Volume slider does nothing | Volume level needs UPnP, which needs discovery. Check the log for `ssdp_rendering_control_location` |
| App list is empty | The list is fetched once at startup, and the `legacy` protocol never returns one. See [apps and app IDs](docs/App_ids.md) |
| `turn_on` does nothing | The TV is on Ethernet and the stored MAC is its Wi-Fi address. Samsung uses a different MAC per interface |
| No `HDMI 1`, `HDMI 2` in the source list | The TV did not answer `ed.sourcesChanged`. The list falls back to `TV`/`HDMI`, which switch by key code |
| Entry goes unavailable randomly | Re-authentication is required; a re-auth dialog will appear |

Download diagnostics from the integration's overflow menu before opening an issue.

## Credits

This integration is maintained by [danalec][danalec].

The protocol layer, config flow and entity model are taken from the official Home Assistant `samsungtv` integration, which
descends from [ha-samsungtv-custom][ha_samsungtv_custom] by [roberodin][roberodin] →
[SamsungTV Tizen][samsungtv_tizen] by [jaruba][jaruba] → [SamsungTV Smart][samsungtv_smart] by [ollo69][ollo69].

Logo support in that lineage was based on [jaruba channel-logos][channels-logo], developed with the support of
[Screwdgeh][screwdgeh]. Logos are not part of this component.

[danalec]: https://github.com/danalec
[ha_samsungtv_custom]: https://github.com/roberodin/ha-samsungtv-custom
[roberodin]: https://github.com/roberodin
[samsungtv_tizen]: https://github.com/jaruba/ha-samsungtv-tizen
[jaruba]: https://github.com/jaruba
[samsungtv_smart]: https://github.com/ollo69/ha-samsungtv-smart
[ollo69]: https://github.com/ollo69
[channels-logo]: https://github.com/jaruba/channel-logos
[screwdgeh]: https://github.com/Screwdgeh
