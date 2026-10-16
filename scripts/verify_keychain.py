"""Verification of the chained-key parser in media_player.py, extracted from source."""
import ast
import asyncio
import sys
import time
import types
import pathlib

# Resolve from this file so the script works from any working directory.
SRC = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "samsungtv_custom"
    / "media_player.py"
)

if not SRC.is_file():
    print(f"FAIL   {SRC} not found")
    sys.exit(1)

tree = ast.parse(SRC.read_text(encoding="utf-8"))

cls = next(
    n
    for n in tree.body
    if isinstance(n, ast.ClassDef) and n.name == "SamsungTVDevice"
)
target = next(
    n
    for n in cls.body
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_async_send_key_chain"
)

# constants the parser closes over, read from the real module
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                try:
                    consts[t.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass

ns = {"asyncio": asyncio, **{k: v for k, v in consts.items() if "KEYPRESS" in k}}
exec(compile(ast.Module(body=[target], type_ignores=[]), str(SRC), "exec"), ns)

send_chain = ns["_async_send_key_chain"]


class Entity:
    """Minimal stand-in recording what the entity would send."""

    def __init__(self):
        self.sent = []

    async def _async_send_keys(self, keys):
        self.sent.append(keys[0])


entity = Entity()
send_chain.__get__(entity)

failures = []


async def run(chain):
    entity.sent.clear()
    start = time.monotonic()
    await send_chain(entity, chain)
    return entity.sent[:], time.monotonic() - start


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(label)
    print("{:<6} {:<48} got={!r}".format("PASS" if ok else "FAIL", label, got))


async def main():
    for const in ("KEYPRESS_MIN_DELAY", "KEYPRESS_MAX_DELAY", "KEYPRESS_DEFAULT_DELAY"):
        print("    {} = {!r}".format(const, ns.get(const)))
    print()

    sent, el = await run("KEY_HOME")
    check("single key", (sent, round(el, 2)), (["KEY_HOME"], 0.0))

    sent, el = await run("KEY_HOME+KEY_EXIT")
    check(
        "two keys get KEYPRESS_DEFAULT_DELAY",
        (len(sent), round(el, 2)),
        (2, round(ns["KEYPRESS_DEFAULT_DELAY"], 2)),
    )

    sent, el = await run("KEY_SOURCES+500+KEY_ENTER")
    check("explicit delay honoured", (sent, round(el, 2)), (["KEY_SOURCES", "KEY_ENTER"], 0.5))

    sent, el = await run("KEY_SOURCES+10+KEY_ENTER")
    check("tiny delay clamped to min", round(el, 2), round(ns["KEYPRESS_MIN_DELAY"], 2))

    sent, el = await run("KEY_SOURCES+99999+KEY_ENTER")
    check("huge delay clamped to max", round(el, 2), round(ns["KEYPRESS_MAX_DELAY"], 2))

    sent, el = await run("KEY_TV+")
    check("trailing plus sends nothing extra", sent, ["KEY_TV"])

    sent, el = await run(" KEY_TV + 100 + KEY_ENTER ")
    check("whitespace tolerated", sent, ["KEY_TV", "KEY_ENTER"])

    # "-100".isdigit() is False, so a signed delay used to fall through to the
    # key branch and be sent to the TV as a key code it silently ignores. The
    # chain then ran with no delay where the author asked for one.
    sent, el = await run("KEY_A+-100+KEY_B")
    check("signed delay is not sent as a key", sent, ["KEY_A", "KEY_B"])
    check("signed negative clamps to min", round(el, 2), round(ns["KEYPRESS_MIN_DELAY"], 2))

    sent, el = await run("KEY_A++100+KEY_B")
    check("leading plus delay is not sent as a key", sent, ["KEY_A", "KEY_B"])

    sent, el = await run("KEY_EXIT+KEY_EXIT+KEY_ENTER")
    check("three keys", sent, ["KEY_EXIT", "KEY_EXIT", "KEY_ENTER"])

    print()
    if failures:
        print("{} CHECK(S) FAILED: {}".format(len(failures), failures))
        sys.exit(1)
    print("all checks passed")


asyncio.run(main())
