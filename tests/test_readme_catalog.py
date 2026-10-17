"""Keep the root README cog catalog consistent with installed cog packages.

This test uses only the Python standard library. It checks presence, not whether
descriptions or examples are semantically current.
"""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ROW_RE = re.compile(r"^\|\s*\[\x60([^\x60]+)\x60\]\(([^)]+)/\)\s*\|", re.MULTILINE)


class ReadmeCatalogTests(unittest.TestCase):
    def test_all_cog_packages_are_listed_once(self):
        actual = set()
        for manifest in ROOT.glob("*/info.json"):
            path = manifest.parent
            if not (path / "__init__.py").is_file():
                continue
            with manifest.open(encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertIsInstance(data, dict, str(manifest))
            actual.add(path.name)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        rows = ROW_RE.findall(readme)
        names = [name for name, _ in rows]
        self.assertEqual(len(names), len(set(names)), "Duplicate cog catalog entries")
        self.assertTrue(all(name == target for name, target in rows),
                        "Catalog cog links must match their package names")
        self.assertSetEqual(set(names), actual,
                            "Update the root README cog table when cogs change")


if __name__ == "__main__":
    unittest.main()
