# AGENTS.md

Home Assistant custom integration (`samsungtv_custom`) that controls Samsung TVs, including 2021+ models. HACS-distributed, config-flow based.

**The integration core is taken from `home-assistant/core` (`components/samsungtv`, `quality_scale: gold`) and adapted to the `samsungtv_custom` domain.** Read that upstream before changing the protocol layer — it is the source of truth, not this repo.

## Setup commands

No build system and no lockfile. This is a plain Python component copied into a Home Assistant config directory; dependencies are declared in the manifest and installed by HA.

- Byte-compile check: `python -m compileall -q custom_components/samsungtv_custom`
- Lint: `ruff check custom_components/samsungtv_custom` (config in `ruff.toml`, which requires ruff >= 0.16.10 — the same floor as upstream; `uvx ruff@0.16.10 check ...` runs it without installing)
- Verification scripts: `python scripts/verify_keychain.py`, `python scripts/verify_imports.py`, `python scripts/verify_strings.py`, `python scripts/verify_repo.py`, `python scripts/verify_protocol.py`, `python scripts/verify_power.py`, `python scripts/verify_sources.py`
- CI: `.github/workflows/hassfest.yaml` validates the manifest, `strings.json` and `triggers.yaml`; `.github/workflows/verify.yaml` runs the lint, byte-compile and all seven verification scripts
- Validate before pushing: `docker run --rm -v "${PWD}:/github/workspace" ghcr.io/home-assistant/hassfest`. Hassfest has real rules that the local gate does not cover — manifest key order, `>=` on requirements Home Assistant already pins, `triggers.yaml`, and the compatibility of each pin against the HA release. It caught seven errors in one run that a green local gate missed.
- Dev install: copy (or symlink) `custom_components/samsungtv_custom/` into `<config>/custom_components/samsungtv_custom/`

**Python 3.14.2+ and Home Assistant 2026.10+ are required.** This is not a preference: the bridge inherited from core uses PEP 649 (lazy annotations) and PEP 758 (`except A, B:` without parentheses), both of which only parse on 3.14+. `ruff.toml` targets `py314` for the same reason.

The two floors are enforced differently, and it matters when you change one:

- **Python** is not declarative. `bridge.py` fails to parse on an older interpreter, which is the enforcement.
- **Home Assistant** is declared in `hacs.json`, which is the only place HACS reads it from. Nothing at runtime checks it, and `const.py` deliberately holds no constant for it — an unread constant that looks like a gate is worse than none. Lowering the floor in `hacs.json` means re-checking the bridge against that HA release's APIs.

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
- `docs/` — `App_ids.md`, `Key_chaining.md`, `Key_codes.md`

### Upstream fidelity

Ten modules are byte-for-byte identical to `home-assistant/core`: `__init__.py`, `config_flow.py`, `coordinator.py`,
`device_trigger.py`, `diagnostics.py`, `helpers.py`, `remote.py`, `trigger.py`, and both files under `triggers/`. Keep
it that way: re-diff against upstream before touching any of them, and never reformat an untouched upstream file to
satisfy a local preference.

Four modules diverge, each marked in the source with "This branch is not upstream" or "not upstream":

- `bridge.py` — three additions, all protocol level. The `ms.error` branch of `_remote_event` treats a `No Authorized`
  reply as an authentication failure, because a TV that refuses the token answers the command and keeps the socket open
  instead of closing it, and `samsungtvws` only converts that into `UnauthorizedError` while opening the channel.
  `parse_sources` and the two `ed.*` helpers add direct input switching. Upstream drops all of it; without the first one
  the entry looks healthy while dropping every key. Pinned by `scripts/verify_protocol.py` and
  `scripts/verify_sources.py`.
- `entity.py` — `async_turn_on` sends a wake-on-LAN packet before running the turn-on automation, because "Samsung TVs
  ignore wake-on-LAN" does not hold for the Neo QLED family. Upstream raises unless an automation is attached. Pinned by
  `scripts/verify_power.py`.
- `media_player.py` — key chaining plus the source list and `select_source` routing for direct switching.
- `const.py` — the domain name.

All four are upstreamable. If any lands in `home-assistant/core`, delete the local block and keep the script.

A local lint ignore is only acceptable when the rule is already on the core ignore list. `ruff.toml` mirrors core's
`pyproject.toml` for exactly this reason; `UP049` is on that list, which is why `bridge.py` can keep the upstream
`_RemoteT` / `_CommandT` type parameter names.

The SmartThings cloud client, the channel/app logos, picture mode and art mode existed in the previous base and were
removed with the base swap. They are recoverable from the `staged/smartthings-and-logos` tag. Re-adding them means
porting against the bridge/coordinator model above, not restoring the old files.

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

Home Assistant is not a dev dependency, so seven standalone scripts verify the pure logic **without installing HA** — they read the real shipped files rather than a copy of them:

- `python scripts/verify_keychain.py` — chained key parsing, delay clamping (extracts `_async_send_key_chain` with `ast`)
- `python scripts/verify_imports.py` — every relative import resolves and the subpackage it needs exists
- `python scripts/verify_strings.py` — `strings.json` and `translations/*.json` agree leaf for leaf, every value is a non-empty string, and no value carries a `[%key:...%]` placeholder that would not resolve outside core
- `python scripts/verify_repo.py` — no `.pyc` tracked, every tracked text file ends with a newline (binary files skipped)
- `python scripts/verify_protocol.py` — which protocol each model gets, and that a refused token starts re-authentication
- `python scripts/verify_power.py` — wake-on-LAN, MAC validation, and the `turn_on` decision matrix
- `python scripts/verify_sources.py` — direct source switching: both reply shapes, the list merge, and the key fallback

Run all seven plus `ruff` and `compileall` before opening a PR. Every one of them has been proven to fail against a copy
of the code with the feature removed — a green that was never seen red proves nothing. Beyond that, validation is manual:

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
