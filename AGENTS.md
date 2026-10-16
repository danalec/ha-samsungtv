# AGENTS.md

Home Assistant custom integration (`samsungtv_custom`) that controls Samsung TVs from 2016 onward. HACS-distributed, config-flow based, and a continuation of [SamsungTV Smart](https://github.com/ollo69/ha-samsungtv-smart), which is itself a fork of [SamsungTV Tizen](https://github.com/jaruba/ha-samsungtv-tizen).

## Setup commands

No build system and no lockfile. This is a plain Python component copied into a Home Assistant config directory; dependencies are declared in the manifest and installed by HA.

- Byte-compile check: `python -m compileall -q custom_components/samsungtv_custom`
- Lint (SOTA rule set): `ruff check --select E9,F,B custom_components/samsungtv_custom`
- Manifest/strings validation: CI runs `home-assistant/actions/hassfest` on every push and PR
- Dev install: copy (or symlink) `custom_components/samsungtv_custom/` into `<config>/custom_components/samsungtv_custom/` of your HA installation

## Project layout

- `custom_components/samsungtv_custom/__init__.py` — setup/unload, entry lifecycle, logo static paths
- `custom_components/samsungtv_custom/config_flow.py` — UI setup, reconfigure and the options flow
- `custom_components/samsungtv_custom/const.py` — every `CONF_*`, defaults, result codes, `DOMAIN`
- `custom_components/samsungtv_custom/media_player.py` — the media player entity, chained keys, entity services
- `custom_components/samsungtv_custom/remote.py` — the `remote` platform entity
- `custom_components/samsungtv_custom/entity.py` — `SamsungTVEntity` base: `DeviceInfo`, `unique_id`, MAC connection
- `custom_components/samsungtv_custom/api/` — protocol layer: `samsungws.py` (websocket + polling thread), `smartthings.py` (cloud API), `samsungcast.py` (cast), `upnp.py`, `shortcuts.py`
- `custom_components/samsungtv_custom/logo.py` + `logo_paths.json` — channel/app logo resolution
- `custom_components/samsungtv_custom/diagnostics.py` — download diagnostics
- `custom_components/samsungtv_custom/strings.json` — source of truth for config/options/service strings
- `custom_components/samsungtv_custom/translations/` — `en`, `hu`, `it`, `pt-BR`; `en.json` mirrors `strings.json`
- `docs/` — `App_list.md`, `Key_chaining.md`, `Key_codes.md`, `Smartthings.md`

## Architecture notes

Protocol and platform selection happen in exactly two places:

- `__init__.py` — `SAMSMART_PLATFORM = [Platform.MEDIA_PLAYER, Platform.REMOTE]`, forwarded on every entry setup
- `media_player.py` — the `SamsungTVWS` object is the single communication handle; SmartThings (`self._st`) is optional and layered on top

Two polling mechanisms coexist and must not be confused:

- `api/samsungws.py` runs a **dedicated `threading.Thread`** for connection keepalive. `time.sleep` there is correct and must not be converted to `asyncio.sleep`.
- `media_player.py` polls from the event loop. Its blocking `send_command` is deliberately offloaded with `hass.async_add_executor_job`, which is why `SamsungTVWS` can stay synchronous.

A change to key sending or power handling usually needs the same edit in `_check_status`, `_async_power_on` and `_async_wait_for_power_on` — they share the SmartThings state and are not independent.

## Code style

- Match Home Assistant core conventions: 4-space indent, double quotes, type hints, `_LOGGER = logging.getLogger(__name__)` per module
- Use `MediaPlayerEntityFeature` — **never** the removed `SUPPORT_*` constants, which is why this fork pinned `homeassistant: 0.90.0` and could not load on modern HA
- `CONF_*` keys are plain lowercase strings declared in `const.py`; do not import new ones from `homeassistant.const`
- Every user-visible string goes in `strings.json` first, then `translations/en.json`, then the other locales
- The TV token is cached under `hass.config.path(STORAGE_DIR, ...)`, **not** in the component folder — never reintroduce a token file in the repo

## Testing instructions

- There is no automated test suite. Do not add one implicitly in unrelated changes
- Validate manually: install into a HA instance, add the integration from the UI, then check the log for the entry being set up and for `media_player`/`remote` entities appearing
- Exercise key chaining end to end: `KEY_SOURCES+500+KEY_ENTER` must open the source menu, and `KEY_EXIT+KEY_EXIT+500+KEY_EXIT` must confirm dialogs
- SmartThings changes need care: `api/smartthings.py` drives **power state** from the `switch.switch.value` component, never from device health. Health is diagnostics only
- Run `ruff check --select E9,F,B` and `compileall` before opening a PR; CI runs hassfest, which validates `manifest.json` and `strings.json`

## PR & commit conventions

- Branch from `master`; never push directly to it
- Conventional commits (`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`) — single line subject, imperative
- Upstream-first: fixes that originate in a sibling fork or in HA core should be sent upstream too. The SmartThings power-state fixes came from the `teichsta/ha-samsungtv` fork

## Security

- Never commit secrets. SmartThings API keys live in the HA config entry; logos may be served from `custom_components/samsungtv_custom/www/`
- Do not commit `.pyc` files. Some are still tracked from the pre-4.0 layout; removing them is a separate cleanup change
- TV control ports (`8001`/`8002`, `55000`) are LAN-only — do not add code that binds or proxies to the public internet