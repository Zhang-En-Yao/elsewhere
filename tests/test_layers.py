"""Each layer imports only the layers inside it: the dependency rule, read off
the source rather than trusted."""

import ast
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "elsewhere"

#: What each layer may import from inside Elsewhere, besides itself and the
#: package's own constants.
ALLOWED = {
    "domain": set(),
    "application": {"domain"},
    "server": {"application", "domain"},
    "adapters": {"domain"},
    "harness": {"server", "application", "domain", "adapters"},
    "interface": {"harness", "server", "application", "domain", "adapters"},
}


def layers_imported(path: Path):
    """The layers one module imports from, by resolving its relative imports."""
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    package = list(parts[:-1])
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                module = base + (node.module.split(".") if node.module else [])
            else:
                module = (node.module or "").split(".")
            if module[0] != "elsewhere":
                continue
            if len(module) > 1:
                yield module[1]
            else:
                yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")
                if module[0] == "elsewhere" and len(module) > 1:
                    yield module[1]


class TestTheDependencyRule(unittest.TestCase):
    def test_every_module_belongs_to_a_layer(self):
        for path in PACKAGE.rglob("*.py"):
            parts = path.relative_to(PACKAGE).parts
            if parts == ("__init__.py",):
                continue
            self.assertIn(parts[0], ALLOWED, f"{path} is in no layer")

    def test_nothing_reaches_outward(self):
        for layer, allowed in ALLOWED.items():
            for path in (PACKAGE / layer).rglob("*.py"):
                for imported in layers_imported(path):
                    if imported == layer or imported not in ALLOWED:
                        continue  # itself, or the package's constants
                    with self.subTest(module=str(path.relative_to(PACKAGE))):
                        self.assertIn(imported, allowed, f"{layer} may not import {imported}")

    def test_the_rule_is_actually_read(self):
        imported = set(layers_imported(PACKAGE / "harness" / "tick.py"))
        self.assertLessEqual({"server", "application", "domain", "adapters"}, imported)


if __name__ == "__main__":
    unittest.main()
