#!/usr/bin/env python3
"""Verify the protocol layer decisions that decide whether a TV is supported.

Two things in bridge.py decide whether a model works, and neither is visible
from the outside until a TV sits on the shelf:

1. model_requires_encryption / model_may_require_encryption, which pick the
   transport. Getting this wrong means the integration talks the wrong
   protocol and the TV ignores every command.
2. the ms.error branch of _remote_event, which decides whether a token the
   TV refused is noticed at all.

Both are read out of the shipped bridge.py with ast, so this exercises real
code rather than a copy of it. Run it directly:

    python scripts/verify_protocol.py
"""

from __future__ import annotations

import ast
import logging
import pathlib
import sys
import types

BRIDGE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "samsungtv_custom"
    / "bridge.py"
)

if not BRIDGE.is_file():
    print(f"FAIL   {BRIDGE} not found")
    sys.exit(1)

TREE = ast.parse(BRIDGE.read_text(encoding="utf-8"))

failures: list[str] = []


def check(label: str, got: object, expected: object) -> None:
    """Compare one value and record the result."""
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"{'PASS' if ok else 'FAIL':<6} {label:<52} got={got!r}")


def load_function(
    name: str, class_name: str | None = None, extra_globals: dict[str, object] | None = None
) -> object:
    """Pull one function definition out of bridge.py and compile it.

    `extra_globals` seeds the namespace with the module-level names the
    function closes over, so the extracted code behaves as it does in the
    real module.
    """
    body = TREE.body
    if class_name is not None:
        cls = next(
            n
            for n in TREE.body
            if isinstance(n, ast.ClassDef) and n.name == class_name
        )
        body = cls.body
    func = next(
        n
        for n in body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    namespace: dict[str, object] = dict(extra_globals or {})
    module = ast.Module(body=[func], type_ignores=[])
    exec(compile(module, str(BRIDGE), "exec"), namespace)  # noqa: S102
    return namespace[name]


def load_constant(name: str) -> object:
    """Read one module-level constant out of bridge.py."""
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise KeyError(name)


# --------------------------------------------------------------------------
# 1. Transport selection per model
# --------------------------------------------------------------------------
print("Transport selection (model -> protocol)")
print()

requires = load_function("model_requires_encryption")
may_require = load_function("model_may_require_encryption")

# (model, requires_encrypted, may_require_encrypted, note)
#
# The rule under test is `len(model) > 4 and model[4] in "HJ"` for the hard
# case and `model[4] == "K"` for the fallback. Neo QLED names put the year
# letter at index 4 too, so every one of them lands on websocket.
MODEL_MATRIX = [
    # The models this change was written for. 2022 Neo QLED, validated live by
    # mbillow/localthings against two QN90B units.
    ("QN90B", False, False, "Neo QLED 90\" 2022 - websocket 8002, no PIN"),
    ("QN80B", False, False, "Neo QLED 80\" 2022"),
    ("Q80B", False, False, "Neo QLED 80\" 2022, 4-char name"),
    ("QN900B", False, False, "Neo QLED 98\" 2022"),
    ("QN85B", False, False, "Neo QLED 85\" 2022"),
    # Later Neo QLED generations: same letter slot, same transport.
    ("QN90C", False, False, "Neo QLED 2023"),
    ("QN90D", False, False, "Neo QLED 2024"),
    ("QN90E", False, False, "Neo QLED 2025"),
    # 2026 Neo QLED reports an H at index 4, which the 2021 H-series rule
    # reads as "needs encrypted". async_get_device_info falls back to
    # websocket when the encrypted connect fails, so this degrades safely -
    # but the entry is created as encrypted first.
    ("QN90H", True, False, "2026 - collides with the H-series rule"),
    # The series the H/J rule was written for.
    ("UN55HU6900", True, False, "2021 H-series"),
    ("UE55JU6800", True, False, "2021 J-series"),
    ("UN55JU6800", True, False, "2021 J-series"),
    # 2016 K-series pairs over websocket but can need the encrypted fallback.
    ("UN55KU6290", False, True, "2016 K-series"),
    ("UN50KJU6300", False, True, "K-series"),
    # Too short to index into.
    ("UN55", False, False, "too short"),
    ("Q80", False, False, "too short"),
    (None, False, False, "unknown model"),
]

for model, expected_required, expected_may, note in MODEL_MATRIX:
    check(
        f"model_requires_encryption({model!r})",
        requires(model),
        expected_required,
    )
    check(
        f"model_may_require_encryption({model!r})",
        may_require(model),
        expected_may,
    )
    print(f"       -> {note}")

# --------------------------------------------------------------------------
# 2. Rejection of the token is noticed
# --------------------------------------------------------------------------
print()
print("Token rejection handling (ms.error branch of _remote_event)")
print()

remote_event = load_function("_remote_event", class_name="SamsungTVWSBridge")
namespace: dict[str, object] = {
    "ED_INSTALLED_APP_EVENT": "ed.installedApp",
    "MS_ERROR_EVENT": "ms.error",
    "parse_installed_app": lambda response: [],
    "parse_sources": load_function(
        "parse_sources", extra_globals={"ED_SOURCES_EVENT": load_constant("ED_SOURCES_EVENT")}
    ),
    "ED_SOURCES_EVENT": load_constant("ED_SOURCES_EVENT"),
    "cast": lambda _type, value: value,
    "LOGGER": logging.getLogger("verify_protocol"),
    "CONF_METHOD": "method",
    "CONF_PORT": "port",
    "METHOD_ENCRYPTED_WEBSOCKET": "encrypted",
    "ENCRYPTED_WEBSOCKET_PORT": 8000,
    "is_auth_error_message": load_function(
        "is_auth_error_message",
        extra_globals={"AUTH_ERROR_MESSAGES": load_constant("AUTH_ERROR_MESSAGES")},
    ),
    "AUTH_ERROR_MESSAGES": load_constant("AUTH_ERROR_MESSAGES"),
}

# Recompile _remote_event against the namespace above.
func_node = next(
    n
    for cls in TREE.body
    if isinstance(cls, ast.ClassDef) and cls.name == "SamsungTVWSBridge"
    for n in cls.body
    if isinstance(n, ast.FunctionDef) and n.name == "_remote_event"
)
exec(  # noqa: S102
    compile(ast.Module(body=[func_node], type_ignores=[]), str(BRIDGE), "exec"),
    namespace,
)
remote_event = namespace["_remote_event"]


class FakeBridge:
    """Minimal stand-in recording what _remote_event decided."""

    def __init__(self) -> None:
        self.host = "192.0.2.10"
        self.auth_failed = False
        self.reauth_calls = 0
        self.config_updates: list[dict[str, object]] = []
        self.app_lists: list[object] = []

    def _notify_app_list_callback(self, app_list: dict[str, str]) -> None:
        self.app_lists.append(app_list)

    def _notify_update_config_entry(self, updates: dict[str, object]) -> None:
        self.config_updates.append(updates)

    def _notify_reauth_callback(self) -> None:
        self.reauth_calls += 1


def fire(response: dict[str, object]) -> FakeBridge:
    """Run _remote_event for one event and report what it did."""
    bridge = FakeBridge()
    event = str(response.get("event"))
    bridge._remote_event = types.MethodType(remote_event, bridge)
    bridge._remote_event(event, response)
    return bridge


def error(message: str | None) -> dict[str, object]:
    """Build the ms.error payload the TV sends."""
    data = {} if message is None else {"message": message}
    return {"event": "ms.error", "data": data}


# The wording observed live on a QN90B when the token is refused.
bridge = fire(error("No Authorized"))
check("No Authorized -> auth_failed", bridge.auth_failed, True)
check("No Authorized -> reauth calls", bridge.reauth_calls, 1)
check("No Authorized -> no config rewrite", bridge.config_updates, [])

for variant in ("no authorized", "Not Authorized", "Unauthorized"):
    bridge = fire(error(variant))
    check(f"case variant {variant!r} -> auth_failed", bridge.auth_failed, True)

# The pre-existing upstream branch must keep working untouched.
bridge = fire(error("unrecognized method value : ms.remote.control"))
check("unrecognized method -> auth_failed", bridge.auth_failed, False)
check("unrecognized method -> reauth calls", bridge.reauth_calls, 0)
check(
    "unrecognized method -> rewrites to encrypted",
    bridge.config_updates,
    [{"method": "encrypted", "port": 8000}],
)

# Anything else must stay quiet.
for unrelated in ("something else went wrong", None):
    bridge = fire(error(unrelated))
    check(f"unrelated {unrelated!r} -> auth_failed", bridge.auth_failed, False)
    check(f"unrelated {unrelated!r} -> reauth calls", bridge.reauth_calls, 0)
    check(f"unrelated {unrelated!r} -> no config rewrite", bridge.config_updates, [])

# A payload with no data at all must not raise.
bridge = fire({"event": "ms.error"})
check("ms.error without data -> auth_failed", bridge.auth_failed, False)

# The app-list branch must be untouched by the new one.
bridge = FakeBridge()
bridge._remote_event = types.MethodType(remote_event, bridge)
bridge._remote_event("ed.installedApp", {"data": {}})
check("ed.installedApp -> no reauth", bridge.reauth_calls, 0)
check("ed.installedApp -> no auth_failed", bridge.auth_failed, False)

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("all checks passed")
