"""Throwaway audit: unused / undefined names after the patch application."""
import ast
import pathlib

root = pathlib.Path("custom_components/samsungtv_custom")
problems = []

for f in sorted(root.rglob("*.py")):
    src = f.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        problems.append(f"FALHA DE SINTAXE {f}: {e}")
        continue

    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported[a.asname or a.name] = node.lineno

    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            v = node.value
            while isinstance(v, ast.Attribute):
                v = v.value
            if isinstance(v, ast.Name):
                used.add(v.id)
    # names referenced inside string annotations
    used |= {t for t in ast.dump(tree).split("'") if t.isidentifier()}

    for name, line in sorted(imported.items(), key=lambda kv: kv[1]):
        if name not in used:
            problems.append(f"import nao usado: {f.name}:{line} -> {name}")

    # module-level constants defined but never referenced
    defined = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    defined[t.id] = node.lineno
    if defined:
        dumps = ast.dump(tree)
        for name, line in sorted(defined.items(), key=lambda kv: kv[1]):
            if f"'{name}'" not in dumps:
                problems.append(f"constante nao usada: {f.name}:{line} -> {name}")

print("\n".join(problems) if problems else "nenhum import/constante orfao")