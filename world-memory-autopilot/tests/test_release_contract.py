"""Release-surface tests for skill metadata, assets, and human documentation."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET

from tests.test_skill_contract import PACKAGE, REFERENCE_PATHS, SKILL_PATH, WORKTREE, _read


README = WORKTREE / "README.md"
AGENTS = WORKTREE / "AGENTS.md"
METADATA = PACKAGE / "agents" / "openai.yaml"
ICON = PACKAGE / "assets" / "icon.svg"


def _parse_small_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, result)]
    for raw_line in _read(path).splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2:
            raise AssertionError("metadata indentation must use two spaces")
        key, separator, raw_value = raw_line.strip().partition(":")
        if not separator or not key:
            raise AssertionError("metadata must use scalar mappings only")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise AssertionError("metadata keys must be unique")
        raw_value = raw_value.strip()
        if not raw_value:
            value: object = {}
            parent[key] = value
            stack.append((indent, value))
            continue
        if len(raw_value) < 2 or raw_value[0] != '"' or raw_value[-1] != '"':
            raise AssertionError("metadata scalar strings must be quoted")
        parent[key] = raw_value[1:-1]
    return result


def _legacy_markers() -> tuple[str, ...]:
    return (
        "targeted" + "-v1",
        "wm" + "c1",
        "Cache" + " Reconciled",
        "Payload" + " Digest",
        "Run" + " Key",
        "Slot" + " Key",
        "verify" + "-precommit",
        "pre" + "commit",
        "post" + "commit",
        "0." + "10.x",
    )


def _installable_paths() -> tuple[Path, ...]:
    """Return the exact regular-file surface consumed by the release builder."""

    paths = [PACKAGE / "SKILL.md", PACKAGE / "requirements.txt"]
    for relative_root in (
        Path("agents"),
        Path("assets"),
        Path("references"),
        Path("scripts/world_memory"),
    ):
        root = PACKAGE / relative_root
        if not root.is_dir():
            raise AssertionError(f"missing installable directory: {relative_root}")
        for candidate in root.rglob("*"):
            if candidate.is_symlink():
                raise AssertionError(f"installable symlink is not allowed: {candidate}")
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(PACKAGE)
            if "__pycache__" in relative.parts or candidate.suffix == ".pyc":
                continue
            paths.append(candidate)
    for path in paths:
        if not path.is_file():
            raise AssertionError(f"missing installable file: {path}")
    return tuple(sorted(paths))


class MetadataAndAssetTests(unittest.TestCase):
    def test_openai_metadata_is_minimal_and_matches_the_runtime_identity(self) -> None:
        metadata = _parse_small_yaml(METADATA)
        self.assertEqual(set(metadata), {"interface"})
        interface = metadata["interface"]
        self.assertIs(type(interface), dict)
        self.assertEqual(
            set(interface),
            {"display_name", "short_description", "icon_small", "icon_large", "default_prompt"},
        )
        self.assertEqual(interface["icon_small"], "./assets/icon.svg")
        self.assertEqual(interface["icon_large"], "./assets/icon.svg")
        default_prompt = interface["default_prompt"]
        for required in (
            "$world-memory-autopilot",
            "notion-native-v2",
            "same-window Report reuse",
            "partial-source continuation",
            "six-hour Story integration",
            "saved Notion views",
            "SQL-free",
        ):
            self.assertIn(required, default_prompt)
        self.assertLessEqual(len(_read(METADATA).splitlines()), 8)

    def test_icon_is_safe_self_contained_svg(self) -> None:
        root = ET.fromstring(_read(ICON).encode("utf-8"))
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")
        forbidden_elements = {"script", "image", "use", "foreignObject"}
        for element in root.iter():
            self.assertNotIn(element.tag.rsplit("}", 1)[-1], forbidden_elements)
            for name, value in element.attrib.items():
                self.assertNotIn(name.rsplit("}", 1)[-1], {"href", "src"})
                self.assertNotRegex(value, r"(?i)(?:https?:|javascript:|data:)")


class DocumentationReleaseBoundaryTests(unittest.TestCase):
    def test_readme_names_the_exact_install_artifact_and_operating_model(self) -> None:
        readme = _read(README)
        required = (
            "world-memory-autopilot-v0.14.0.zip",
            "World Memory · Notion Native",
            "World Memory Collections",
            "World Memory Stories",
            "World Memory Story Changes",
            "World Memory Reports",
            "notion-native-v2",
            "six-hour default interval",
            "creationCadenceMinutes=360",
            "six-hour Story",
            "partial source",
            "0.10.x",
            "rollback-only",
            "not auto-migrated",
            "Reports Recent",
            "Stories Current",
            "VIX9D",
            "VIX3M",
            "VIX6M",
            "public CSV",
            "pause",
            "regenerate",
            "read-only",
            "resume",
        )
        for value in required:
            self.assertIn(value, readme)
        self.assertIn(
            "Allow setup and schema-create permissions only during bootstrap, then reduce access to normal read/write after the live canary",
            readme,
        )
        self.assertIn(
            "four database containers, each with an initial data source",
            readme,
        )
        self.assertEqual(readme.count("0.10.x"), 1)
        self.assertRegex(
            readme,
            r"v0\.11\.x.*pause.*regenerate.*notion-native-v2.*Reports Recent.*Stories Current.*public CSV.*resume",
        )

    def test_local_agents_constitution_is_short_untracked_and_outside_package(self) -> None:
        lines = _read(AGENTS).splitlines()
        self.assertGreaterEqual(len(lines), 60)
        self.assertLessEqual(len(lines), 90)
        self.assertFalse((PACKAGE / "AGENTS.md").exists())
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "AGENTS.md"],
            cwd=WORKTREE,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(tracked.returncode, 0)

    def test_release_resolver_calculates_the_actual_installable_file_set(self) -> None:
        paths = _installable_paths()
        relative = {path.relative_to(PACKAGE).as_posix() for path in paths}
        self.assertEqual(len(paths), 23)

        for required in (
            "SKILL.md",
            "requirements.txt",
            "agents/openai.yaml",
            "assets/icon.svg",
            "references/notion-layout.md",
            "scripts/world_memory/__init__.py",
            "scripts/world_memory/cli.py",
            "scripts/world_memory/discovery.py",
            "scripts/world_memory/plugin_market.py",
        ):
            self.assertIn(required, relative)
        forbidden_fragments = (
            "AGENTS.md",
            "credentials",
            "raw-plugin-capture",
            "normalizer-fixture",
            "__pycache__",
            ".pyc",
            "/plans/",
            "/specs/",
        )
        for path in relative:
            self.assertFalse(path.startswith("tests/"), path)
            self.assertNotIn(path, {"AGENTS.md", "README.md"})
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, path, path)
            self.assertTrue(
                path in {"SKILL.md", "requirements.txt"}
                or path.startswith("agents/")
                or path.startswith("assets/")
                or path.startswith("references/")
                or path.startswith("scripts/world_memory/"),
                path,
            )

    def test_actual_installable_text_has_no_legacy_runtime_machinery_real_ids_or_secrets(self) -> None:
        uuid_pattern = re.compile(
            r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
        )
        secret_patterns = (
            re.compile(r"(?i)Bearer\s+[A-Za-z0-9._-]{16,}"),
            re.compile(r"(?i)sk-[A-Za-z0-9_-]{16,}"),
        )
        for path in _installable_paths():
            text = _read(path)
            for marker in _legacy_markers():
                self.assertNotIn(marker, text, f"{marker} in {path.name}")
            self.assertIsNone(uuid_pattern.search(text), path.name)
            for pattern in secret_patterns:
                self.assertIsNone(pattern.search(text), path.name)

    def test_readme_allows_one_explicit_rollback_only_legacy_version_reference(self) -> None:
        readme = _read(README)
        self.assertEqual(readme.count("0.10.x"), 1)
        self.assertRegex(readme, r"Old `0\.10\.x` artifacts are rollback-only archives\.")


if __name__ == "__main__":
    unittest.main()
