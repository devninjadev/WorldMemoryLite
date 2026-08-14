"""Black-box tests for the deterministic World Memory release builder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from scripts.build_world_memory_release import build_release


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "world-memory-autopilot"


def _independent_installable_paths(package: Path) -> tuple[Path, ...]:
    paths = [package / "SKILL.md", package / "requirements.txt"]
    for root in ("agents", "assets", "references", "scripts/world_memory"):
        paths.extend(
            path
            for path in (package / root).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    return tuple(sorted(paths))


class ReleaseBuilderContractTests(unittest.TestCase):
    def _copy_package(self, destination: Path) -> Path:
        copied = destination / "world-memory-autopilot"
        shutil.copytree(PACKAGE, copied, symlinks=True)
        return copied

    def test_builds_exact_installable_surface_with_source_byte_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "release.zip"
            receipt = build_release(PACKAGE, output)
            expected = [path.relative_to(PACKAGE).as_posix() for path in _independent_installable_paths(PACKAGE)]
            self.assertEqual(len(expected), 21)
            self.assertEqual(receipt["version"], "0.12.0")
            self.assertEqual(receipt["topLevel"], ["world-memory-autopilot"])
            self.assertEqual(receipt["entries"], [f"world-memory-autopilot/{path}" for path in expected])
            self.assertEqual(len(receipt["entries"]), 21)
            self.assertEqual(receipt["size"], output.stat().st_size)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.namelist(), receipt["entries"])
                for relative in expected:
                    self.assertEqual(
                        archive.read(f"world-memory-autopilot/{relative}"),
                        (PACKAGE / relative).read_bytes(),
                        relative,
                    )

    def test_cli_without_arguments_builds_the_named_release_next_to_its_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._copy_package(root)
            scripts = root / "scripts"
            scripts.mkdir()
            builder = scripts / "build_world_memory_release.py"
            shutil.copy2(ROOT / "scripts" / "build_world_memory_release.py", builder)

            result = subprocess.run(
                ["python3", str(builder)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            receipt = json.loads(result.stdout)
            output = root / "world-memory-autopilot-v0.12.0.zip"
            self.assertTrue(output.is_file())
            self.assertEqual(receipt["version"], "0.12.0")
            self.assertEqual(receipt["size"], output.stat().st_size)

    def test_is_byte_reproducible_and_receipt_hash_matches_independent_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first.zip", root / "second.zip"
            first_receipt = build_release(PACKAGE, first)
            second_receipt = build_release(PACKAGE, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            expected_hash = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertRegex(first_receipt["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(first_receipt["sha256"], expected_hash)
            self.assertEqual(second_receipt["sha256"], expected_hash)

    def test_ignores_runtime_python_cache_without_archiving_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._copy_package(root)
            cache = package / "scripts" / "world_memory" / "__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "workflow.cpython-312.pyc").write_bytes(b"runtime-cache")
            output = root / "release.zip"
            receipt = build_release(package, output)
            expected = [
                f"world-memory-autopilot/{path.relative_to(package).as_posix()}"
                for path in _independent_installable_paths(package)
            ]
            self.assertEqual(receipt["entries"], expected)
            self.assertFalse(any("__pycache__" in entry or entry.endswith(".pyc") for entry in expected))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), expected)
                for source in _independent_installable_paths(package):
                    entry = f"world-memory-autopilot/{source.relative_to(package).as_posix()}"
                    self.assertEqual(archive.read(entry), source.read_bytes(), entry)

    def test_rejects_unsafe_package_inputs_before_replacing_existing_output(self) -> None:
        cases = (
            ("unexpected", lambda package: (package / "references" / "unexpected.txt").write_text("x")),
            ("secret", lambda package: (package / "references" / "deployment.md").write_text((package / "references" / "deployment.md").read_text() + "\nBearer " + "a" * 24)),
            ("uuid", lambda package: (package / "references" / "deployment.md").write_text((package / "references" / "deployment.md").read_text() + "\n12345678-1234-4123-8123-123456789abc")),
            ("legacy", lambda package: (package / "references" / "deployment.md").write_text((package / "references" / "deployment.md").read_text() + "\nprecommit postcommit 0.10.x")),
            ("version", lambda package: (package / "SKILL.md").write_text((package / "SKILL.md").read_text().replace("`0.12.0`", "`0.12.1`"))),
            ("missing", lambda package: (package / "requirements.txt").unlink()),
        )
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = self._copy_package(root)
                output = root / "release.zip"
                sentinel = b"known-good-output"
                output.write_bytes(sentinel)
                mutate(package)
                with self.assertRaises(ValueError):
                    build_release(package, output)
                self.assertEqual(output.read_bytes(), sentinel)

    def test_rejects_symlink_and_cli_rejects_missing_parent_and_source_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._copy_package(root)
            (package / "references" / "linked.md").symlink_to(package / "SKILL.md")
            with self.assertRaises(ValueError):
                build_release(package, root / "release.zip")
            missing_parent = root / "missing" / "release.zip"
            command = ["python3", str(ROOT / "scripts" / "build_world_memory_release.py"), "--package", str(PACKAGE), "--output", str(missing_parent)]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertRegex(result.stderr, r"^[a-z-]+\n$")
            alias = PACKAGE / "SKILL.md"
            result = subprocess.run(command[:-1] + [str(alias)], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertRegex(result.stderr, r"^[a-z-]+\n$")


if __name__ == "__main__":
    unittest.main()
