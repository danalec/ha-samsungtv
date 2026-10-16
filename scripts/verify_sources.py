#!/usr/bin/env python3
"""Verify direct input source switching.

Two halves, because the feature spans two files:

- bridge.parse_sources turns the TV's ed.sourcesChanged reply into
  {name: id}. Firmware nests that payload in two different ways, and a
  wrong guess would be worse than not having the feature, so the parser is
  expected to return an empty mapping for anything it does not recognise.
- media_player decides what the source list contains and which route a
  selection takes: exact switch by id, app launch, or key fallback.

Both are read out of the shipped files with ast. Run it directly:

    python scripts/verify_sources.py
"""

from __future__ import annotations

import ast
import asyncio
import logging
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "samsungtv_custom"
BRIDGE = COMPONENT / "bridge.py"
MEDIA_PLAYER = COMPONENT / "media_player.py"

for required in (BRIDGE, MEDIA_PLAYER):
    if not required.is_file():
        print(f"FAIL   {required} not found")
        sys.exit(1)

BRIDGE_TREE = ast.parse(BRIDGE.read_text(encoding="utf-8"))
MEDIA_TREE = ast.parse(MEDIA_PLAYER.read_text(encoding="utf-8"))

failures: list[str] = []


def check(label: str, got: object, expected: object) -> None:
    """Compare one value and record the result."""
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"{'PASS' if ok else 'FAIL':<6} {label:<58} got={got!r}")


def load_function(
    tree: ast.Module,
    path: pathlib.Path,
    name: str,
    class_name: str | None = None,
    extra_globals: dict[str, object] | None = None,
) -> object:
    """Pull one definition out of a module and compile it.

    A missing definition is a hard failure with a message, not a traceback:
    it means the feature this script guards is not in the component at all.
    """
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
    namespace: dict[str, object] = dict(extra_globals or {})
    exec(  # noqa: S102
        compile(ast.Module(body=[func], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[name]


def load_constant(tree: ast.Module, name: str) -> object:
    """Read one module-level constant."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    print(f"FAIL   constant {name} not found - the feature is missing")
    sys.exit(1)


parse_sources = load_function(
    BRIDGE_TREE,
    BRIDGE,
    "parse_sources",
    extra_globals={"ED_SOURCES_EVENT": load_constant(BRIDGE_TREE, "ED_SOURCES_EVENT")},
)

TV_SOURCES = [
    {"id": "hdmi:1,0", "name": "HDMI 1", "ispc": False},
    {"id": "hdmi:2,0", "name": "HDMI 2", "ispc": False},
    {"id": "tv", "name": "Terrestrial", "ispc": False},
]
EXPECTED = {"HDMI 1": "hdmi:1,0", "HDMI 2": "hdmi:2,0", "Terrestrial": "tv"}

# --------------------------------------------------------------------------
# 1. Parsing the reply
# --------------------------------------------------------------------------
print("parse_sources")
print()

check(
    "event in the envelope",
    parse_sources(
        "ed.sourcesChanged",
        {"event": "ed.sourcesChanged", "data": {"sources": TV_SOURCES}},
    ),
    EXPECTED,
)
check(
    "event nested inside data",
    parse_sources(
        "ms.channel.emit",
        {
            "event": "ms.channel.emit",
            "data": {
                "event": "ed.sourcesChanged",
                "data": {"sources": TV_SOURCES},
            },
        },
    ),
    EXPECTED,
)
check(
    "unrelated event",
    parse_sources("ed.apps.launch", {"event": "ed.apps.launch", "data": {}}),
    {},
)
check(
    "missing data",
    parse_sources("ed.sourcesChanged", {"event": "ed.sourcesChanged"}),
    {},
)
check(
    "sources not a list",
    parse_sources(
        "ed.sourcesChanged",
        {"event": "ed.sourcesChanged", "data": {"sources": "nope"}},
    ),
    {},
)
check(
    "entries without name or id are skipped",
    parse_sources(
        "ed.sourcesChanged",
        {
            "event": "ed.sourcesChanged",
            "data": {
                "sources": [
                    {"id": "hdmi:1,0", "name": "HDMI 1"},
                    {"id": "hdmi:2,0"},
                    {"name": "no id"},
                    {"id": 7, "name": "wrong type"},
                    "not a dict",
                ]
            },
        },
    ),
    {"HDMI 1": "hdmi:1,0"},
)
check(
    "non-dict response",
    parse_sources("ed.sourcesChanged", ["not", "a", "dict"]),
    {},
)
check(
    "empty sources list",
    parse_sources(
        "ed.sourcesChanged", {"event": "ed.sourcesChanged", "data": {"sources": []}}
    ),
    {},
)

# --------------------------------------------------------------------------
# 2. The source list the entity exposes
# --------------------------------------------------------------------------
print()
print("source list")
print()

SOURCES = {"TV": "KEY_TV", "HDMI": "KEY_HDMI"}

update_sources = load_function(
    MEDIA_TREE,
    MEDIA_PLAYER,
    "_update_sources",
    class_name="SamsungTVDevice",
    extra_globals={"SOURCES": SOURCES},
)


class FakeSourceEntity:
    """Stand-in exposing only what _update_sources touches."""

    _sources: dict[str, str] | None
    _app_list: dict[str, str] | None

    def __init__(self, sources: dict[str, str] | None, apps: dict[str, str] | None) -> None:
        self._sources = sources
        self._app_list = apps
        self._attr_source_list: list[str] = []
        self.update_sources = types.MethodType(update_sources, self)
        self.update_sources()


check(
    "no reports: static sources only",
    FakeSourceEntity(None, None)._attr_source_list,
    ["TV", "HDMI"],
)
check(
    "reported inputs replace the generic HDMI",
    FakeSourceEntity({"HDMI 1": "hdmi:1,0", "HDMI 2": "hdmi:2,0"}, None)._attr_source_list,
    ["TV", "HDMI 1", "HDMI 2"],
)
check(
    "reported inputs supersede the static ones entirely",
    FakeSourceEntity({"TV": "tv", "HDMI 1": "hdmi:1,0"}, None)._attr_source_list,
    ["TV", "HDMI 1"],
)
check(
    "an unrelated reported name keeps the static entries",
    FakeSourceEntity({"Terrestrial": "tv"}, None)._attr_source_list,
    ["TV", "HDMI", "Terrestrial"],
)
check(
    "apps are appended last",
    FakeSourceEntity(
        {"HDMI 1": "hdmi:1,0"}, {"Netflix": "11101200001"}
    )._attr_source_list,
    ["TV", "HDMI 1", "Netflix"],
)
check(
    "apps only",
    FakeSourceEntity(None, {"Netflix": "11101200001"})._attr_source_list,
    ["TV", "HDMI", "Netflix"],
)

# --------------------------------------------------------------------------
# 3. Which route a selection takes
# --------------------------------------------------------------------------
print()
print("async_select_source routing")
print()


class HomeAssistantError(Exception):
    """Stand-in for the real one; only its presence matters here."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(kwargs.get("translation_key", "error"))
        self.kwargs = kwargs


select_source = load_function(
    MEDIA_TREE,
    MEDIA_PLAYER,
    "async_select_source",
    class_name="SamsungTVDevice",
    extra_globals={
        "SOURCES": SOURCES,
        "HomeAssistantError": HomeAssistantError,
        "DOMAIN": "samsungtv_custom",
        "override": lambda func: func,
    },
)


class FakeBridge:
    """Records what the entity asked the bridge to do."""

    def __init__(self) -> None:
        self.selected: list[str] = []

    async def async_select_source(self, source_id: str) -> None:
        self.selected.append(source_id)


class FakeSelectEntity:
    """Stand-in for the parts of SamsungTVDevice select_source touches."""

    def __init__(self, sources: dict[str, str] | None, apps: dict[str, str] | None) -> None:
        self._sources = sources
        self._app_list = apps
        self._bridge = FakeBridge()
        self.launched: list[str] = []
        self.keys: list[str] = []
        self.entity_id = "media_player.samsung_tv"
        self.select_source = types.MethodType(select_source, self)

    async def _async_launch_app(self, app_id: str) -> None:
        self.launched.append(app_id)

    async def _async_send_keys(self, keys: list[str]) -> None:
        self.keys.extend(keys)


def select_for(
    source: str, sources: dict[str, str] | None, apps: dict[str, str] | None
) -> tuple[FakeSelectEntity, str | None]:
    """Run select_source and report which error came out, if any."""
    entity = FakeSelectEntity(sources, apps)
    try:
        asyncio.run(entity.select_source(source))
    except HomeAssistantError as err:
        return entity, err.kwargs.get("translation_key")
    return entity, None


entity, error = select_for("HDMI 2", {"HDMI 1": "hdmi:1,0", "HDMI 2": "hdmi:2,0"}, None)
check("known input -> exact switch by id", entity._bridge.selected, ["hdmi:2,0"])
check("known input -> no key fallback", entity.keys, [])
check("known input -> no error", error, None)

entity, error = select_for("HDMI", None, None)
check("static source without a report -> key fallback", entity.keys, ["KEY_HDMI"])
check("static source without a report -> no switch", entity._bridge.selected, [])
check("static source without a report -> no error", error, None)

entity, error = select_for("Netflix", {"HDMI 1": "hdmi:1,0"}, {"Netflix": "11101200001"})
check("app name -> app launch", entity.launched, ["11101200001"])
check("app name -> no switch", entity._bridge.selected, [])

entity, error = select_for("Nope", {"HDMI 1": "hdmi:1,0"}, None)
check("unknown source -> source_unsupported", error, "source_unsupported")

# A TV that reported a source literally named "HDMI" must not be shadowed by
# the static entry, but must still resolve.
entity, error = select_for("HDMI", {"HDMI": "hdmi:0,0"}, None)
check("reported name shadows the static key", entity._bridge.selected, ["hdmi:0,0"])

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("all checks passed")
