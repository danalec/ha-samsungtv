#!/usr/bin/env python3
"""Verify the translation payload of the component.

Home Assistant treats strings.json as the source of truth and loads
translations/en.json as the rendered English. For a custom component those
two must agree exactly: a key that exists in one and not the other shows up
as a missing or a stray label in the UI, and nothing else catches it.

This also enforces two rules that are easy to break and invisible until a
user sees them:

- every value must be a non-empty string;
- no value may contain a [%key:...%] reference. Core's strings use those to
  point at core's own translations; in a custom component the reference does
  not resolve and the user sees the raw placeholder.

Run it directly: python scripts/verify_strings.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "samsungtv_custom"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations"

# [%key:component::samsungtv::config::step::user::data::host%]
PLACEHOLDER = re.compile(r"\[%key:[^\]]*%\]")


def leaves(node: object, prefix: str = "") -> dict[str, object]:
    """Flatten nested translation objects to leaf paths.

    A leaf is any non-dict value. A key whose value is an empty dict has no
    leaf, which is what the parity check wants to see.
    """
    if isinstance(node, dict):
        out: dict[str, object] = {}
        for key, value in node.items():
            out.update(leaves(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node}


def check_json(path: Path) -> tuple[dict[str, object], list[str]]:
    """Load a translation file and return its leaves plus any problems."""
    problems: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        return {}, [f"{path.name}: cannot be read ({err})"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        return {}, [f"{path.name}: invalid JSON at line {err.lineno} ({err.msg})"]

    flat = leaves(data)

    for path_key, value in flat.items():
        if not isinstance(value, str):
            problems.append(f"{path.name}: {path_key} is {type(value).__name__}, not a string")
            continue
        if not value.strip():
            problems.append(f"{path.name}: {path_key} is an empty string")
        if match := PLACEHOLDER.search(value):
            problems.append(
                f"{path.name}: {path_key} contains unresolvable placeholder {match.group(0)!r}"
            )

    return flat, problems


def main() -> int:
    if not STRINGS.is_file():
        print(f"FAIL   strings.json not found at {STRINGS}")
        return 1

    base, problems = check_json(STRINGS)
    if not base:
        print("FAIL   strings.json has no leaf keys")
        return 1

    print(f"       strings.json: {len(base)} leaf keys")

    failures = list(problems)

    files = sorted(TRANSLATIONS.glob("*.json"))
    if not files:
        failures.append("translations/ has no files")
        print("FAIL   no translations found")
        return 1

    for path in files:
        translated, file_problems = check_json(path)
        failures.extend(file_problems)

        missing = sorted(set(base) - set(translated))
        extra = sorted(set(translated) - set(base))

        for key in missing:
            failures.append(f"{path.name}: missing key {key}")
        for key in extra:
            failures.append(f"{path.name}: key not in strings.json: {key}")

        status = "PASS" if not (missing or extra or file_problems) else "FAIL"
        print(
            f"{status}   {path.name}: {len(translated)} leaf keys"
            f", {len(missing)} missing, {len(extra)} extra"
        )

    if failures:
        print(f"\n{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
