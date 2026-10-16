"""Verification of the chained-key parser in media_player.py, extracted from source."""
import ast
import asyncio
import sys
import types
import pathlib

SRC = pathlib.Path("custom_components/samsungtv_custom/media_player.py")
tree = ast.parse(SRC.read_text(encoding="utf-8"))

cls = next(
    n
    for n in tree.body
    if isinstance(n, ast.ClassDef) and n.name == "SamsungTVDevice"
)
target = next(
    n
    for n in cls.body
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_async_send_keys"
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

ns = {
    "asyncio": asyncio,
    "STStatus": types.SimpleNamespace(STATE_ON="ON"),
    **{k: v for k, v in consts.items() if "KEYPRESS" in k or "ST_" in k},
}
exec(compile(ast.Module(body=[target], type_ignores=[]), str(SRC), "exec"), ns)

send_keys = ns["_async_send_keys"]


class Entity:
    """Minimal stand-in recording what the entity would send."""

    def __init__(self):
        self.sent = []
        self.st_calls = []

    async def async_send_command(self, key):
        self.sent.append(key)
        return True

    async def _smartthings_keys(self, key):
        self.st_calls.append(key)


entity = Entity()
send_keys.__get__(entity)

failures = []


async def run(chain):
    entity.sent.clear()
    entity.st_calls.clear()
    t0 = asyncio.get_event_loop().time() if False else None
    import time
    start = time.monotonic()
    result = await send_keys(entity, chain)
    return entity.sent[:], entity.st_calls[:], result, time.monotonic() - start


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(label)
    print("{:<6} {:<48} got={!r}".format("PASS" if ok else "FAIL", label, got))


async def main():
    for const in ("KEYPRESS_MIN_DELAY", "KEYPRESS_MAX_DELAY", "KEYPRESS_DEFAULT_DELAY"):
        print("    {} = {!r}".format(const, ns.get(const)))
    print()

    sent, st, res, _ = await run("KEY_HOME")
    check("single key", (sent, res), (["KEY_HOME"], True))

    sent, st, res, el = await run("KEY_HOME+KEY_EXIT")
    check(
        "two keys get KEYPRESS_DEFAULT_DELAY",
        (len(sent), round(el, 2)),
        (2, round(ns["KEYPRESS_DEFAULT_DELAY"], 2)),
    )

    sent, st, res, el = await run("KEY_SOURCES+500+KEY_ENTER")
    check("explicit delay honoured", (sent, round(el, 2)), (["KEY_SOURCES", "KEY_ENTER"], 0.5))

    sent, st, res, el = await run("KEY_SOURCES+50+KEY_ENTER")
    check("tiny delay clamped to min", round(el, 2) >= round(ns["KEYPRESS_MIN_DELAY"], 2), True)

    sent, st, res, el = await run("KEY_SOURCES+99999+KEY_ENTER")
    check("huge delay clamped to max", round(el, 2), round(ns["KEYPRESS_MAX_DELAY"], 2))

    sent, st, res, _ = await run("ST_TV")
    check("ST_ prefix routes to SmartThings", (sent, st), ([], ["ST_TV"]))

    sent, st, res, _ = await run("KEY_EXIT+ST_TV")
    check("mixed chain splits correctly", (sent, st), (["KEY_EXIT"], ["ST_TV"]))

    sent, st, res, _ = await run("KEY_HOME+KEY_EXIT+KEY_ENTER")
    check("three keys", sent, ["KEY_HOME", "KEY_EXIT", "KEY_ENTER"])

    print()
    if failures:
        print("{} CHECK(S) FAILED: {}".format(len(failures), failures))
        sys.exit(1)
    print("all checks passed")


asyncio.run(main())