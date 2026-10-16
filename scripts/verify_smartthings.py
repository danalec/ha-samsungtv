"""Verification of the SmartThings parsing helpers, extracted from the real source.

Not part of the shipped component: it pulls the functions out of
api/smartthings.py with ast so we exercise the shipped code, not a copy.
"""
import ast
import json
import sys
import types
import pathlib

SRC = pathlib.Path(
    "custom_components/samsungtv_custom/api/smartthings.py"
)

tree = ast.parse(SRC.read_text(encoding="utf-8"))

# fake the enum + logger the helpers close over
STStatus = types.SimpleNamespace(STATE_OFF="OFF", STATE_ON="ON", STATE_UNKNOWN="UNKNOWN")
_LOGGER = types.SimpleNamespace(
    debug=lambda *a, **k: None, warning=lambda *a, **k: None
)

ns = {"STStatus": STStatus, "_LOGGER": _LOGGER, "json": json}

picked = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in (
        "_switch_value_to_state", "_volume_value_to_ratio",
    ):
        picked.append(node)
    if isinstance(node, ast.ClassDef) and node.name == "SmartThingsTV":
        for sub in node.body:
            if isinstance(sub, ast.FunctionDef) and sub.name == "_load_json_list":
                picked.append(sub)

missing = {"_switch_value_to_state", "_volume_value_to_ratio", "_load_json_list"} - {
    n.name for n in picked
}
if missing:
    sys.exit("could not extract: {}".format(sorted(missing)))

exec(compile(ast.Module(body=picked, type_ignores=[]), str(SRC), "exec"), ns)

switch_state = ns["_switch_value_to_state"]
volume_ratio = ns["_volume_value_to_ratio"]
load_json_list = ns["_load_json_list"]

failures = []


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(label)
    print("{:<6} {:<52} got={!r}".format("PASS" if ok else "FAIL", label, got))


print("--- switch value -> power state ---")
check("bool True -> ON", switch_state(True), "ON")
check("bool False -> OFF", switch_state(False), "OFF")
check("'on' -> ON", switch_state("on"), "ON")
check("'off' -> OFF", switch_state("off"), "OFF")
check("'ON' uppercase -> ON", switch_state("ON"), "ON")
check("'  Off  ' padded -> OFF", switch_state("  Off  "), "OFF")
check("'' empty -> OFF", switch_state(""), "OFF")
check("'   ' whitespace -> OFF", switch_state("   "), "OFF")
check("'maybe' garbage -> OFF", switch_state("maybe"), "OFF")
check("None -> OFF", switch_state(None), "OFF")
check("int 1 -> OFF (not bool)", switch_state(1), "OFF")
check("dict -> OFF", switch_state({"value": "on"}), "OFF")
check("list -> OFF", switch_state(["on"]), "OFF")

print()
print("--- volume value -> 0..1 ratio ---")
check("'35' -> 0.35", volume_ratio("35"), 0.35)
check("'0' -> 0.0", volume_ratio("0"), 0.0)
check("'100' -> 1.0", volume_ratio("100"), 1.0)
check("35 int -> 0.35 (no AttributeError)", volume_ratio(35), 0.35)
check("35.7 float truncates -> 0.35", volume_ratio(35.7), 0.35)
check("None -> 0.0", volume_ratio(None), 0.0)
check("'' -> 0.0", volume_ratio(""), 0.0)
check("'abc' -> 0.0", volume_ratio("abc"), 0.0)
check("dict -> 0.0", volume_ratio({"value": 35}), 0.0)

print()
print("--- _load_json_list ---")
check("JSON string decodes", load_json_list({"x": {"value": '["a","b"]'}}, "x"), ["a", "b"])
check("already-decoded list passes through", load_json_list({"x": {"value": ["a"]}}, "x"), ["a"])
check("missing key -> []", load_json_list({}, "x"), [])
check("None value -> []", load_json_list({"x": {"value": None}}, "x"), [])
check("garbage string -> []", load_json_list({"x": {"value": "not json"}}, "x"), [])
check("empty string -> []", load_json_list({"x": {"value": ""}}, "x"), [])
check("dict value -> []", load_json_list({"x": {"value": {"a": 1}}}, "x"), [])

print()
if failures:
    print("{} CHECK(S) FAILED: {}".format(len(failures), failures))
    sys.exit(1)
print("all checks passed")