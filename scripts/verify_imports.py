"""Audit every relative import in the integration and report unresolvable ones.

A missing subpackage is invisible to compileall and to ruff, but it breaks the
integration at import time in Home Assistant.
"""
import ast
import pathlib
import sys

# Resolve from this file, not from the current working directory. A hardcoded
# relative path made this script report "0 imports, all fine" and exit 0 when
# run from anywhere but the repository root - a silent green that checked
# nothing at all.
ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "samsungtv_custom"

if not COMPONENT.is_dir():
    print(f"FAIL   component directory not found: {COMPONENT}")
    sys.exit(1)

sources = sorted(COMPONENT.rglob("*.py"))
if not sources:
    print(f"FAIL   no Python modules found under {COMPONENT}")
    sys.exit(1)

broken = []
checked = 0


def resolves(path: pathlib.Path) -> bool:
    """True when the path is an importable module or package."""
    return path.with_suffix(".py").exists() or (path / "__init__.py").exists()


for f in sources:
    tree = ast.parse(f.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue

        base = f.parent
        for _ in range(node.level - 1):
            base = base.parent

        # `from . import x` has no module part: x itself must be a module.
        if node.module is None:
            for alias in node.names:
                checked += 1
                if not resolves(base / alias.name):
                    broken.append(
                        f"{f}:{node.lineno}: from {'.' * node.level} import "
                        f"{alias.name}  -> {base / alias.name} nao existe"
                    )
            continue

        # The module part itself must resolve. Names imported *from* a resolved
        # module cannot be checked without executing it, and that is fine:
        # ruff F821 already covers undefined names.
        target = base / node.module.replace(".", "/")
        checked += 1
        if not resolves(target):
            broken.append(
                f"{f}:{node.lineno}: from {'.' * node.level}{node.module} import ..."
                f"  -> {target} nao existe"
            )

print(f"{checked} imports relativos verificados em {len(sources)} modulos")
if checked == 0:
    print("FAIL   nenhum import relativo encontrado: a verificacao nao verificou nada")
    sys.exit(1)
if broken:
    print(f"\n{len(broken)} IMPORT(S) QUEBRADO(S):")
    for b in broken:
        print("  " + b)
    sys.exit(1)
print("nenhum import relativo quebrado")
