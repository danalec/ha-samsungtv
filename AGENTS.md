# AGENTS.md

Home Assistant custom integration (`samsungtv_custom`) that controls Samsung TVs, including 2021+ models. HACS-distributed, config-flow based.

**The integration core is taken from `home-assistant/core` (`components/samsungtv`, `quality_scale: gold`) and adapted to the `samsungtv_custom` domain.** Read that upstream before changing the protocol layer — it is the source of truth, not this repo.

## Setup commands

No build system and no lockfile. This is a plain Python component copied into a Home Assistant config directory; dependencies are declared in the manifest and installed by HA.

- Byte-compile check: `python -m compileall -q custom_components/samsungtv_custom`
- Lint: `ruff check custom_components/samsungtv_custom` (config in `ruff.toml`)
- Verification scripts: `python scripts/verify_smartthings.py`, `scripts/verify_keychain.py`, `scripts/verify_imports.py`
- Manifest/strings validation: CI runs `home-assistant/actions/hassfest` on every push and PR
- Dev install: copy (or symlink) `custom_components/samsungtv_custom/` into `<config>/custom_components/samsungtv_custom/`

**Python 3.14.2+ and Home Assistant 2026.10+ are required.** This is not a preference: the bridge inherited from core uses PEP 649 (lazy annotations) and PEP 758 (`except A, B:` without parentheses), both of which only parse on 3.14+. `ruff.toml` targets `py314` for the same reason. Do not lower `__min_ha_version__` in `const.py` without re-checking the bridge.

## Project layout

- `__init__.py` — entry lifecycle, bridge creation, SSDP location updates, debounced reload
- `bridge.py` — protocol layer from core: `legacy` (55000), `websocket` (8001/8002), `encrypted` (8000, 2021+ TVs)
- `coordinator.py` — `DataUpdateCoordinator`; every entity reads from `entry.runtime_data`
- `entity.py` — `SamsungTVEntity` base: `DeviceInfo`, `unique_id`
- `config_flow.py` — UI setup, reauth, reconfigure, encrypted PIN pairing
- `media_player.py` — media player entity, plus this repo's `send_key` media type and chained keys
- `remote.py` — the `remote` platform entity
- `device_trigger.py`, `trigger.py` — device automation for turn on/off
- `helpers.py` — shared helpers
- `diagnostics.py` — download diagnostics
- `strings.json` — source of truth for config/exceptions/trigger strings
- `quality_scale.yaml` — honest rule-by-rule status; see Testing for why it is silver
- `docs/` — `App_list.md`, `Key_chaining.md`, `Key_codes.md`, `Smartthings.md`

### Not wired up yet

`api/smartthings.py`, `api/samsungcast.py`, `api/shortcuts.py`, `logo.py` and `logo_paths.json` are carried over from the previous base and are **currently not imported by any module**. They hold the SmartThings cloud integration, channel/app logos, picture mode and art mode. Re-wiring them against the bridge/coordinator model is the next substantial piece of work; until then they are dead weight in the release payload and the corresponding options are not offered.

## Architecture notes

- One communication handle: `SamsungTVBridge`, obtained via `SamsungTVBridge.get_bridge(...)` in `__init__.py` and stored on the coordinator. Entities never talk to the protocol directly.
- State flows one way: coordinator polls the bridge, entities read `coordinator.data` and are notified through `_handle_coordinator_update`. Do not add a second polling path.
- `PARALLEL_UPDATES = 0` in `media_player.py`: entities must not run their own concurrent updates.
- Key sending goes through `_async_send_keys(keys: list[str])`, which enforces the power-off-in-progress guard. Chained keys build on top of it via `_async_send_key_chain`.
- Discovery populates the SSDP locations consumed by UPnP volume/mute; without discovery those features degrade.

## Code style

- Match Home Assistant core conventions: 4-space indent, double quotes, `@override` on entity interface methods, `LOGGER = logging.getLogger(__package__)` from `const.py`
- Every user-visible string goes in `strings.json`. **Core's `[%key:component::samsungtv::...%]` and `[%key:common::...%]` references do not resolve in a custom component** — the values must be literals
- Use `MediaPlayerEntityFeature`, never the removed `SUPPORT_*` constants
- The TV token is cached under `hass.config.path(STORAGE_DIR, ...)`; never reintroduce a token file in the repo

## Testing instructions

There is no pytest-homeassistant suite, which is precisely why `quality_scale.yaml` declares **silver and not gold**: `test-before-setup`, `test-before-configure`, `test-coverage` and `config-flow-test-coverage` are all marked `todo` there. Do not raise the level without the tests to back it.

Home Assistant is not a dev dependency, so three standalone scripts verify the pure parsing logic **without installing HA** — they extract the real functions from the source with `ast`, so they test shipped code rather than a copy:

- `python scripts/verify_smartthings.py` — SmartThings switch/volume/json-list parsing, full type matrix
- `python scripts/verify_keychain.py` — chained key parsing, delay clamping
- `python scripts/verify_imports.py` — no orphaned imports or module constants after a patch

Run all three plus `ruff` and `compileall` before opening a PR. Beyond that, validation is manual:

- Install into a HA instance, add the integration from the UI, then check the log for the entry being set up and for `media_player`/`remote` entities appearing
- Exercise key chaining end to end: `KEY_SOURCES+500+KEY_ENTER` must open the source menu
- For a 2021+ TV the entry must settle on the `encrypted` method on port 8000; a `legacy` fallback there means the model was not detected and the TV will refuse keys

## PR & commit conventions

- Branch from `master`; never push directly to it
- Conventional commits (`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`) — single line subject, imperative
- Upstream-first: fixes that belong in the bridge belong in `home-assistant/core`. Anything else that originates in a sibling fork should be sent there too

## Security

- Never commit secrets. The TV token is obtained through the config flow and stored by HA
- Do not commit `.pyc` files
- TV control ports are LAN-only — do not add code that binds or proxies to the public internet