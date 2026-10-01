"""Check the declared Notion schema tables against the connector-neutral model."""

import copy
from pathlib import Path
import unittest

from world_memory.notion_layout import DATABASE_SCHEMAS, HUB_MARKER

REFERENCE_PATHS = {"notion-layout": Path(__file__).resolve().parents[1] / "references/notion-layout.md"}


def _read(path):
    return path.read_text()


def _table_after(text: str, heading: str) -> list[list[str]]:
    marker = heading + "\n"
    if marker not in text:
        raise AssertionError(f"missing table heading: {heading}")
    tail = text.split(marker, 1)[1].lstrip("\n")
    lines = tail.splitlines()
    table: list[list[str]] = []
    started = False
    for line in lines:
        if line.startswith("|"):
            started = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            table.append(cells)
        elif started:
            break
    if len(table) < 3:
        raise AssertionError(f"table under {heading} is incomplete")
    return table


def _parse_schema_table(text: str, key: str) -> dict[str, dict[str, object]]:
    table = _table_after(text, f"### Schema: {key}")
    expected_header = ["Property", "Type", "Required", "Values or target", "Cardinality"]
    if table[0] != expected_header:
        raise AssertionError(f"schema header for {key} is invalid")
    parsed: dict[str, dict[str, object]] = {}
    for cells in table[2:]:
        if len(cells) != 5:
            raise AssertionError(f"schema row for {key} has the wrong width")
        name, property_type, required, values, cardinality = cells
        descriptor: dict[str, object] = {
            "type": property_type,
            "required": {"yes": True, "no": False}[required],
            "cardinality": cardinality,
        }
        if values.startswith("options="):
            descriptor["options"] = values.removeprefix("options=").split(",")
        elif values.startswith("target="):
            pieces = values.split(";")
            descriptor["target"] = pieces[0].removeprefix("target=")
            if len(pieces) == 2:
                descriptor["self"] = pieces[1] == "self=true"
        elif values != "—":
            raise AssertionError(f"unknown schema values cell: {values}")
        parsed[name] = descriptor
    return parsed


def _documented_schema(descriptor: dict[str, object], property_name: str) -> dict[str, object]:
    expected = copy.deepcopy(descriptor)
    if expected["type"] == "multi_select":
        cardinality = "many"
    elif expected["type"] == "relation" and property_name != "Primary Story":
        cardinality = "many"
    else:
        cardinality = "one"
    expected["cardinality"] = cardinality
    return expected



class DocumentedSchemaTests(unittest.TestCase):
    def test_layout_document_matches_every_runtime_schema_descriptor(self) -> None:
        text = _read(REFERENCE_PATHS["notion-layout"])
        self.assertIn(HUB_MARKER, text)
        for key, schema in DATABASE_SCHEMAS.items():
            documented = _parse_schema_table(text, key)
            expected = {
                name: _documented_schema(descriptor, name)
                for name, descriptor in schema["properties"].items()
            }
            self.assertEqual(documented, expected, key)

