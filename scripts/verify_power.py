#!/usr/bin/env python3
"""Verify how the integration turns a TV on.

`async_turn_on` decides between three outcomes, and the decision used to be
binary: run the attached automation, or fail. It now sends a wake-on-lan
packet first when a usable MAC is known, which matters because the documented
"Samsung TVs ignore wake-on-LAN" is not true for the Neo QLED family.

The order matters. The packet goes out first and the automation runs
afterwards, so a setup that already relied on the automation keeps behaving
the same way, and a setup without one stops raising service_unsupported.

The method is extracted from the shipped entity.py with ast and driven against
stubs, so this exercises real code. Run it directly:

    python scripts/verify_power.py
"""

from __future__ import annotations

import ast
import asyncio
import copy
import functools
import logging
import pathlib
import re
import sys
import types

ENTITY = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "samsungtv_custom"
    / "entity.py"
)
MEDIA_PLAYER = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "samsungtv_custom"
    / "media_player.py"
)

for required in (ENTITY, MEDIA_PLAYER):
    if not required.is_file():
        print(f"FAIL   {required} not found")
        sys.exit(1)

TREE = ast.parse(ENTITY.read_text(encoding="utf-8"))
MEDIA_TREE = ast.parse(MEDIA_PLAYER.read_text(encoding="utf-8"))
failures: list[str] = []


def check(label: str, got: object, expected: object) -> None:
    """Compare one value and record the result."""
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"{'PASS' if ok else 'FAIL':<6} {label:<56} got={got!r}")


def load_function(
    name: str,
    class_name: str | None = None,
    extra_globals: dict[str, object] | None = None,
    tree: ast.Module | None = None,
    path: pathlib.Path | None = None,
) -> object:
    """Pull one definition out of a module and compile it.

    A missing definition is a hard failure with a message, not a traceback:
    it means the feature this script guards is not in the component at all.
    """
    tree = tree if tree is not None else TREE
    path = path if path is not None else ENTITY
    body = tree.body
    if class_name is not None:
        body = next(
            (
                n.body
                for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == class_name
            ),
            None,
        )
    if body is None:
        print(f"FAIL   class {class_name} not found in {path.name}")
        sys.exit(1)
    func = next(
        (
            n
            for n in body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
        ),
        None,
    )
    if func is None:
        where = f"{class_name}." if class_name else ""
        print(f"FAIL   {path.name} defines no {where}{name} - the feature is missing")
        sys.exit(1)
    # Decorators are dropped: every one in this component is either a no-op
    # marker (@override, @callback) or @property, and a property object cannot
    # be bound with MethodType. The functions are driven by hand anyway.
    func = copy.deepcopy(func)
    func.decorator_list = []
    namespace: dict[str, object] = dict(extra_globals or {})
    exec(  # noqa: S102
        compile(ast.Module(body=[func], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[name]


class HomeAssistantError(Exception):
    """Stand-in for the real one; only its presence matters here."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(kwargs.get("translation_key", "error"))
        self.kwargs = kwargs


class ServiceUnsupported(HomeAssistantError):
    """Raised when turn_on has nothing to do."""


def service_unsupported(**kwargs: object) -> HomeAssistantError:
    """Build the error the real method raises."""
    return ServiceUnsupported(**kwargs)


sent: list[str] = []


def send_magic_packet(mac: str, broadcast_address: str | None = None) -> None:
    """Record the packet instead of putting it on the wire."""
    sent.append(mac)


is_valid_mac = load_function("is_valid_mac")

# MAC_RE is built by a re.compile call, so it has to be executed rather than
# literal_eval'd. The pattern still comes from the shipped source.
mac_re_node = next(
    (
        node
        for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MAC_RE" for t in node.targets)
    ),
    None,
)
if mac_re_node is None:
    print("FAIL   MAC_RE not found in entity.py")
    sys.exit(1)

mac_namespace: dict[str, object] = {"re": re}
exec(  # noqa: S102
    compile(ast.Module(body=[mac_re_node], type_ignores=[]), str(ENTITY), "exec"),
    mac_namespace,
)
is_valid_mac.__globals__["MAC_RE"] = mac_namespace["MAC_RE"]

turn_on = load_function(
    "async_turn_on",
    class_name="SamsungTVEntity",
    extra_globals={
        "LOGGER": logging.getLogger("verify_power"),
        "HomeAssistantError": HomeAssistantError,
        "DOMAIN": "samsungtv_custom",
        "partial": functools.partial,
        "send_magic_packet": send_magic_packet,
        "is_valid_mac": is_valid_mac,
    },
)

# --------------------------------------------------------------------------
# MAC validation
# --------------------------------------------------------------------------
print("MAC validation")
print()
for mac in (
    "00:11:22:33:44:55",
    "AA:BB:CC:DD:EE:FF",
    "00-11-22-33-44-55",
    "001122334455",
):
    check(f"is_valid_mac({mac!r})", is_valid_mac(mac), True)

for mac in (None, "", "not-a-mac", "00:11:22:33:44", "00:11:22:33:44:55:66", "zz:11:22:33:44:55"):
    check(f"is_valid_mac({mac!r})", is_valid_mac(mac), False)

# --------------------------------------------------------------------------
# The turn-on decision
# --------------------------------------------------------------------------
print()
print("turn_on decision matrix")
print()


class FakeAction:
    """Stand-in for PluggableAction."""

    def __init__(self) -> None:
        self.runs = 0

    async def async_run(self, hass: object, context: object) -> None:
        self.runs += 1


class FakeHass:
    """Stand-in for Home; runs the executor job inline."""

    def __init__(self) -> None:
        self.jobs: list[object] = []

    async def async_add_executor_job(self, job: object, *args: object) -> object:
        self.jobs.append(job)
        return job(*args)  # type: ignore[operator]


class FakeEntity:
    """Stand-in for SamsungTVEntity."""

    def __init__(self, mac: str | None, action: FakeAction | None) -> None:
        self._mac = mac
        self._host = "192.0.2.10"
        self.entity_id = "media_player.samsung_tv"
        self._turn_on_action = action
        self._context = None
        self.hass = FakeHass()


def turn_on_for(mac: str | None, with_action: bool) -> tuple[FakeEntity, str | None]:
    """Run turn_on and report which error came out, if any."""
    global sent
    sent = []
    action = FakeAction() if with_action else None
    entity = FakeEntity(mac, action)
    entity.async_turn_on = types.MethodType(turn_on, entity)
    try:
        asyncio.run(entity.async_turn_on())
    except HomeAssistantError as err:
        return entity, err.kwargs.get("translation_key")
    return entity, None


valid_mac = "00:11:22:33:44:55"

entity, error = turn_on_for(valid_mac, with_action=False)
check("valid MAC, no automation -> packet sent", sent, [valid_mac])
check("valid MAC, no automation -> no error", error, None)

action_entity, error = turn_on_for(valid_mac, with_action=True)
check("valid MAC, with automation -> packet sent", sent, [valid_mac])
check(
    "valid MAC, with automation -> automation still runs",
    action_entity._turn_on_action.runs,  # type: ignore[union-attr]
    1,
)
check("valid MAC, with automation -> no error", error, None)

entity, error = turn_on_for(None, with_action=True)
check("no MAC, with automation -> no packet", sent, [])
check("no MAC, with automation -> automation runs", entity._turn_on_action.runs, 1)  # type: ignore[union-attr]
check("no MAC, with automation -> no error", error, None)

entity, error = turn_on_for(None, with_action=False)
check("no MAC, no automation -> no packet", sent, [])
check("no MAC, no automation -> service_unsupported", error, "service_unsupported")

entity, error = turn_on_for("garbage", with_action=False)
check("malformed MAC, no automation -> no packet", sent, [])
check("malformed MAC, no automation -> service_unsupported", error, "service_unsupported")

entity, error = turn_on_for("garbage", with_action=True)
check("malformed MAC, with automation -> no packet", sent, [])
check("malformed MAC, with automation -> automation runs", entity._turn_on_action.runs, 1)  # type: ignore[union-attr]

# --------------------------------------------------------------------------
# 3. The entity advertises what it can actually do
# --------------------------------------------------------------------------
print()
print("supported_features advertises TURN_ON")
print()


class MediaPlayerEntityFeature:
    """Stand-in for the real flag enum; ints so `|` behaves like a Flag."""

    TURN_ON = 4
    OTHER = 1


supported_features = load_function(
    "supported_features",
    class_name="SamsungTVDevice",
    extra_globals={
        "MediaPlayerEntityFeature": MediaPlayerEntityFeature,
        "is_valid_mac": is_valid_mac,
        "override": lambda func: func,
    },
    tree=MEDIA_TREE,
    path=MEDIA_PLAYER,
)


class FakeFeatureEntity:
    """Stand-in for the parts of SamsungTVDevice the property touches."""

    _attr_supported_features = MediaPlayerEntityFeature.OTHER
    _mac: str | None
    _turn_on_action: FakeAction | None

    def __init__(self, mac: str | None, with_action: bool) -> None:
        self._mac = mac
        self._turn_on_action = FakeAction() if with_action else None
        self.features = types.MethodType(supported_features, self)


def features_for(mac: str | None, with_action: bool) -> int:
    entity = FakeFeatureEntity(mac, with_action)
    return entity.features()


check(
    "valid MAC, no automation -> TURN_ON advertised",
    bool(features_for(valid_mac, with_action=False) & MediaPlayerEntityFeature.TURN_ON),
    True,
)
check(
    "automation, no MAC -> TURN_ON advertised",
    bool(features_for(None, with_action=True) & MediaPlayerEntityFeature.TURN_ON),
    True,
)
check(
    "neither -> TURN_ON not advertised",
    bool(features_for(None, with_action=False) & MediaPlayerEntityFeature.TURN_ON),
    False,
)
check(
    "malformed MAC, no automation -> TURN_ON not advertised",
    bool(features_for("garbage", with_action=False) & MediaPlayerEntityFeature.TURN_ON),
    False,
)

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("all checks passed")
