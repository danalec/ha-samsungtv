#!/usr/bin/env python3
"""Verify the installed-app list parser in bridge.py, extracted from source.

Upstream builds the app list with samsungtvws' `parse_installed_app`, which is
`return event["data"]["data"]` with no validation, and then subscripts every
entry twice: `app["name"]` and `app["appId"]`.

That runs inside the websocket receive loop, where an exception is terminal.
The library wraps the loop in `suppress(ConnectionClosed)` only, so a KeyError
or TypeError here ends the recv task for good. `is_alive()` keeps answering
True because the socket stays open, so the bridge hands out a dead remote and
never reconnects: inbound frames stop arriving while outbound keys keep being
written to a socket nobody reads. `close()` re-raises the same exception, so it
also escapes the unload and the turn-off path.

`parse_installed_apps` replaces that with the same guards `parse_sources` uses:
every level is type-checked, and anything unrecognised yields an empty mapping.
An app list that cannot be read is not worth losing the connection over.

Read out of the shipped file with ast. Run it directly:

    python scripts/verify_apps.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

SRC = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "samsungtv_custom"
    / "bridge.py"
)

if not SRC.is_file():
    print(f"FAIL   {SRC} not found")
    sys.exit(1)

tree = ast.parse(SRC.read_text(encoding="utf-8"))

try:
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "parse_installed_apps"
    )
except StopIteration:
    print("FAIL   bridge.py has no parse_installed_apps; the app list is unguarded")
    sys.exit(1)

node.decorator_list = []
ns: dict[str, object] = {"Any": object}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(SRC), "exec"), ns)
parse_installed_apps = ns["parse_installed_apps"]

failures: list[str] = []


def check(label: str, got: object, expected: object) -> None:
    """Compare one value and record the result."""
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"{'PASS' if ok else 'FAIL':<6} {label:<58} got={got!r}")


def check_no_raise(label: str, response: object) -> None:
    """The parser must degrade to an empty mapping, never raise.

    A raise here is the crash: it is unrecoverable inside the receive loop.
    """
    try:
        got = parse_installed_apps(response)
    except BaseException as err:  # noqa: BLE001 - the raise is the defect
        failures.append(f"{label}: raised {type(err).__name__}: {err}")
        print(f"{'FAIL':<6} {label:<58} raised {type(err).__name__}: {err}")
        return
    ok = got == {}
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {{}}")
    print(f"{'PASS' if ok else 'FAIL':<6} {label:<58} got={got!r}")


def apps(*entries: object) -> dict[str, object]:
    """Wrap app entries the way a real ed.installedApp.get reply nests them."""
    return {"event": "ed.installedApp.get", "data": {"data": list(entries)}}


# ------------------------------------------------------------------ happy path
check(
    "single app parsed",
    parse_installed_apps(apps({"name": "Netflix", "appId": "111299001912"})),
    {"Netflix": "111299001912"},
)
check(
    "several apps parsed",
    parse_installed_apps(
        apps(
            {"name": "YouTube", "appId": "111299001913"},
            {"name": "Netflix", "appId": "111299001912"},
        )
    ),
    {"YouTube": "111299001913", "Netflix": "111299001912"},
)
check(
    "keys are sorted by name, as upstream did",
    list(parse_installed_apps(
        apps(
            {"name": "Zulu", "appId": "3"},
            {"name": "Alpha", "appId": "1"},
            {"name": "Mike", "appId": "2"},
        )
    )),
    ["Alpha", "Mike", "Zulu"],
)
check(
    "extra keys on an app are ignored",
    parse_installed_apps(
        apps({"name": "TV", "appId": "0", "icon": "x", "is_ad": False})
    ),
    {"TV": "0"},
)
check("empty app list", parse_installed_apps(apps()), {})

# --------------------------------------------------- shapes that used to raise
check_no_raise("response is None", None)
check_no_raise("response is a list", [])
check_no_raise("response is a string", "ed.installedApp.get")
check_no_raise("response is a number", 42)
check_no_raise("response is empty", {})
check_no_raise("data is null", {"data": None})
check_no_raise("data is a string", {"data": "payload"})
check_no_raise("data is a list", {"data": []})
check_no_raise("data is empty", {"data": {}})
check_no_raise("data.data is null", {"data": {"data": None}})
check_no_raise("data.data is a string", {"data": {"data": "apps"}})
check_no_raise("data.data is a dict", {"data": {"data": {"name": "TV"}}})
check_no_raise("entries are junk", apps(None, 1, "x", [], {}))
check_no_raise("entry missing appId", apps({"name": "TV"}))
check_no_raise("entry missing name", apps({"appId": "0"}))
check_no_raise("name is null", apps({"name": None, "appId": "0"}))
check_no_raise("appId is null", apps({"name": "TV", "appId": None}))
check_no_raise("name is a number", apps({"name": 7, "appId": "0"}))
check_no_raise("appId is a number", apps({"name": "TV", "appId": 0}))
check_no_raise("name is empty", apps({"name": "", "appId": "0"}))
check_no_raise("appId is empty", apps({"name": "TV", "appId": ""}))

# A partial list still yields whatever was readable, rather than all of it.
check(
    "readable entries survive alongside junk",
    parse_installed_apps(
        apps(None, {"name": "TV", "appId": "0"}, {"name": None, "appId": "1"}, "junk")
    ),
    {"TV": "0"},
)

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("all checks passed")