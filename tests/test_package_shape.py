"""Release invariants independent of editorial wording and historical layouts."""

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "world-memory-autopilot"


class PackageShapeTests(unittest.TestCase):
    def test_markdown_references_resolve_within_the_package(self):
        for path in (PACKAGE / "SKILL.md", *(PACKAGE / "references").glob("*.md")):
            for target in re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", path.read_text()):
                if ":" in target or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                with self.subTest(document=path.name, target=target):
                    self.assertTrue(resolved.is_relative_to(PACKAGE.resolve()))
                    self.assertTrue(resolved.is_file())

    def test_version_file_and_entrypoint_agree(self):
        version = (PACKAGE / "VERSION").read_text().strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"Version: `{version}`", (PACKAGE / "SKILL.md").read_text())

    def test_icon_is_self_contained_and_contains_no_active_content(self):
        root = ET.fromstring((PACKAGE / "assets/icon.svg").read_bytes())
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")
        for element in root.iter():
            self.assertNotIn(element.tag.rsplit("}", 1)[-1],
                             {"script", "image", "use", "foreignObject"})
            for name, value in element.attrib.items():
                self.assertNotIn(name.rsplit("}", 1)[-1], {"href", "src"})
                self.assertNotRegex(value, r"(?i)(?:https?:|javascript:|data:)")
