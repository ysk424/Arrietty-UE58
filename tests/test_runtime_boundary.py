import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "arrietty_up"


class RuntimeBoundaryTests(unittest.TestCase):
    def test_game_package_does_not_import_bpy(self):
        violations = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    violations.extend(
                        f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}"
                        for alias in node.names
                        if alias.name == "bpy" or alias.name.startswith("bpy.")
                    )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "bpy" or module.startswith("bpy."):
                        violations.append(
                            f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}"
                        )

        self.assertEqual(violations, [], f"runtime bpy imports: {violations}")


if __name__ == "__main__":
    unittest.main()
