"""JSON Schemas in schemas/: the example and new sites pass them, and every field the engine
uses is described (so editors and AI assistants get complete hints).

A tiny validator for the subset of JSON Schema the files use — no dependencies needed.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREE = json.loads((ROOT / "schemas/family_tree.schema.json").read_text(encoding="utf-8"))
SITE = json.loads((ROOT / "schemas/site.schema.json").read_text(encoding="utf-8"))
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def check(value, schema, root, path="$"):
    errors = []
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    t = schema.get("type")
    if t:
        allowed = t if isinstance(t, list) else [t]
        ok = any((x == "integer" and isinstance(value, int) and not isinstance(value, bool)) or
                 (x == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or
                 (x in TYPES and isinstance(value, TYPES[x])) for x in allowed)
        if not ok:
            return [f"{path}: expected {t}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errors.append(f"{path}: missing {k}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                errors += check(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                errors.append(f"{path}: unknown key {k}")
            elif isinstance(extra, dict):
                errors += check(v, extra, root, f"{path}.{k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10 ** 9):
            errors.append(f"{path}: wrong number of items")
        if schema.get("uniqueItems") and len(set(map(json.dumps, value))) != len(value):
            errors.append(f"{path}: items repeat")
        for i, v in enumerate(value):
            prefix = schema.get("prefixItems", [])
            item = prefix[i] if i < len(prefix) else schema.get("items")
            if item:
                errors += check(v, item, root, f"{path}[{i}]")
    return errors


def described(value, schema, root, path="$"):
    """Keys present in the data but not described in the schema."""
    missing = []
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    if isinstance(value, dict) and "properties" in schema:
        for k, v in value.items():
            if k in schema["properties"]:
                missing += described(v, schema["properties"][k], root, f"{path}.{k}")
            elif not isinstance(schema.get("additionalProperties", True), dict):
                missing.append(f"{path}.{k}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for v in value:
            missing += described(v, schema["items"], root, path + "[]")
    return sorted(set(missing))


class Schemas(unittest.TestCase):
    def test_example_passes(self):
        data = json.loads((ROOT / "example/family_tree.json").read_text(encoding="utf-8"))
        self.assertEqual(check(data, TREE, TREE), [])
        site = json.loads((ROOT / "example/site.json").read_text(encoding="utf-8"))
        self.assertEqual(check(site, SITE, SITE), [])

    def test_every_field_is_described(self):
        data = json.loads((ROOT / "example/family_tree.json").read_text(encoding="utf-8"))
        self.assertEqual(described(data, TREE, TREE), [])

    def test_catches_mistakes(self):
        data = json.loads((ROOT / "example/family_tree.json").read_text(encoding="utf-8"))
        data["people"][0]["sex"] = "male"
        data["people"][1]["birth"] = {"date": "before the war"}
        errors = check(data, TREE, TREE)
        self.assertTrue(any("sex" in e for e in errors))
        self.assertTrue(any("birth.date" in e for e in errors))
        self.assertTrue(check({"title": "x", "langauges": ["en"]}, SITE, SITE))

    def test_gedcom_import_passes(self):
        import sys
        sys.path.insert(0, str(ROOT / "tests"))
        from test_ged_import import SAMPLE
        from gene_archive.ged_import import import_gedcom
        data = import_gedcom(SAMPLE)
        self.assertEqual(check(data, TREE, TREE), [])
        self.assertEqual(described(data, TREE, TREE), [])

    def test_new_sites_point_to_the_schemas(self):
        from gene_archive import cli
        with tempfile.TemporaryDirectory() as tmp:
            cli.main(["init", tmp, "--lang", "ru"])
            data = json.loads(Path(tmp, "family_tree.json").read_text(encoding="utf-8"))
            site = json.loads(Path(tmp, "site.json").read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], TREE["$id"])
            self.assertEqual(site["$schema"], SITE["$id"])
            self.assertEqual(check(data, TREE, TREE), [])
            self.assertEqual(check(site, SITE, SITE), [])


if __name__ == "__main__":
    unittest.main()
