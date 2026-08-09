import ast
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (PROJECT_ROOT / "servolab", PROJECT_ROOT / "tests")
UI_COMPATIBILITY_FILES = {
    Path("servolab/app.py"),
    Path("servolab/theme.py"),
    Path("servolab/ui_widgets.py"),
}
COMPATIBILITY_FILES = UI_COMPATIBILITY_FILES | {
    Path("servolab/commands.py"),
    Path("servolab/controllers.py"),
    Path("servolab/custom_controller.py"),
    Path("servolab/disturbances.py"),
    Path("servolab/history.py"),
    Path("servolab/motor.py"),
}


def imported_module(path, node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    module = node.module or ""
    if not node.level:
        return [module]
    package = list(path.relative_to(PROJECT_ROOT).with_suffix("").parts[:-1])
    keep = max(len(package) - node.level + 1, 0)
    base = package[:keep] + ([*module.split(".")] if module else [])
    if module:
        return [".".join(base)]
    return [".".join(base + [alias.name]) for alias in node.names]


def project_python_files():
    yield PROJECT_ROOT / "main.py"
    for root in SOURCE_ROOTS:
        yield from root.rglob("*.py")


class ArchitectureTests(unittest.TestCase):
    def test_python_files_and_functions_stay_within_limits(self):
        violations = []
        for path in project_python_files():
            source = path.read_text(encoding="utf-8")
            line_count = len(source.splitlines())
            if line_count > 500:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}: {line_count} lines")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                span = node.end_lineno - node.lineno + 1
                if span > 100:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                        f"{node.name}: {span} lines"
                    )
        self.assertEqual(violations, [], "\n".join(violations))

    def test_non_ui_modules_do_not_import_desktop_dependencies(self):
        violations = []
        for path in (PROJECT_ROOT / "servolab").rglob("*.py"):
            relative = path.relative_to(PROJECT_ROOT)
            if "ui" in relative.parts or relative in UI_COMPATIBILITY_FILES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                for name in imported_module(path, node):
                    if name == "PyQt5" or name.startswith("PyQt5."):
                        violations.append(f"{relative}:{node.lineno} imports {name}")
                    if name == "pyqtgraph" or name.startswith("pyqtgraph."):
                        violations.append(f"{relative}:{node.lineno} imports {name}")
                    if name == "servolab.ui" or name.startswith("servolab.ui."):
                        violations.append(f"{relative}:{node.lineno} imports {name}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_compatibility_modules_only_reexport_symbols(self):
        allowed_nodes = (ast.Expr, ast.Import, ast.ImportFrom)
        violations = []
        for relative in COMPATIBILITY_FILES:
            path = PROJECT_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                is_public_symbols = (
                    isinstance(node, ast.Assign)
                    and all(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
                )
                if not isinstance(node, allowed_nodes) and not is_public_symbols:
                    violations.append(f"{relative}:{node.lineno} contains {type(node).__name__}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_core_imports_without_desktop_dependencies(self):
        script = """
import importlib.abc
import sys

class BlockDesktopImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'PyQt5' or fullname.startswith('PyQt5.'):
            raise ImportError(fullname)
        if fullname == 'pyqtgraph' or fullname.startswith('pyqtgraph.'):
            raise ImportError(fullname)
        return None

sys.meta_path.insert(0, BlockDesktopImports())
from servolab.config import ExperimentConfig
from servolab.control import CustomControllerProcess
from servolab.plant import PMSMMotor
from servolab.services import SimulationSession
from servolab.simulation import ServoSimulation

simulation = ServoSimulation(ExperimentConfig())
simulation.run_offline(0.01)
assert simulation.last_sample
assert not any(name == 'PyQt5' or name.startswith('PyQt5.') for name in sys.modules)
assert not any(name == 'pyqtgraph' or name.startswith('pyqtgraph.') for name in sys.modules)
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_generated_controller_functions_stay_within_limit(self):
        from servolab.config import ControlConfig, LoopMode, MotorConfig, allowed_reference_types
        from servolab.custom_controller import (
            ControllerGenerationOptions,
            generate_custom_controller_code,
        )

        options = ControllerGenerationOptions(True, True, True, True, True)
        violations = []
        for mode in LoopMode:
            for reference_type in allowed_reference_types(mode):
                source = generate_custom_controller_code(
                    mode,
                    reference_type,
                    ControlConfig(mode=mode),
                    MotorConfig(),
                    options,
                )
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.FunctionDef):
                        span = node.end_lineno - node.lineno + 1
                        if span > 100:
                            violations.append(
                                f"{mode.value}/{reference_type.value}/{node.name}: {span}"
                            )
        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
