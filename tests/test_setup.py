import pathlib
import unittest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


class PyprojectTests(unittest.TestCase):
    def test_runtime_dependencies_include_wcwidth(self):
        pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        deps = data["project"]["dependencies"]
        self.assertIn("wcwidth", deps)

    def test_runtime_dependencies_include_blessed(self):
        pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        deps = data["project"]["dependencies"]
        self.assertIn("blessed", deps)


if __name__ == "__main__":
    unittest.main()
