#!/usr/bin/env python3
"""Repository hygiene checks that no linter covers.

Two invariants that are cheap to keep and easy to break by accident:

- no byte-compiled Python is tracked. A .pyc is machine-specific and makes
  the release payload larger for nothing;
- every tracked text file ends with a newline. Files that miss one produce
  "\\ No newline at end of file" noise in every diff that touches them, and
  POSIX tooling treats the last line as different.

Binary files are skipped: they are not text and are not required to end
with a newline. They are detected by failing to decode as UTF-8.

Only files git already tracks are inspected, so untracked scratch files do
not fail the run. Run it directly: python scripts/verify_repo.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def tracked_files() -> list[str]:
    """List files git tracks in the current worktree."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except FileNotFoundError:
        print("FAIL   git executable not found on PATH")
        raise SystemExit(1) from None
    except subprocess.CalledProcessError as err:
        print(f"FAIL   `git ls-files` failed: {err.stderr.strip() or err}")
        raise SystemExit(1) from None
    return [name for name in out.split("\0") if name]


def is_text(data: bytes) -> bool:
    """Return True when the payload decodes as UTF-8 text."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def main() -> int:
    names = tracked_files()
    if not names:
        print("FAIL   git tracks no files; is this a git repository?")
        return 1

    failures: list[str] = []

    for name in names:
        if name.endswith((".pyc", ".pyo")):
            failures.append(f"{name}: byte-compiled Python is tracked")

    text_count = 0
    for name in names:
        path = Path(name)
        try:
            data = path.read_bytes()
        except OSError as err:
            failures.append(f"{name}: cannot be read ({err})")
            continue
        if not data:
            continue
        if not is_text(data):
            continue
        text_count += 1
        if not data.endswith(b"\n"):
            failures.append(f"{name}: no trailing newline")

    print(f"       {len(names)} tracked files, {text_count} of them text")

    if failures:
        print(f"\n{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
