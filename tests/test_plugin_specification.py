"""The implementation intake keeps the PRD and design success contract aligned."""

import re
import unittest
from pathlib import Path


class PluginSpecificationTests(unittest.TestCase):
    def test_specification_pair_has_identical_observable_criteria_and_links(self):
        root = Path(__file__).resolve().parents[1]
        documents = [(root / folder / "0009-plugin-structure.md").read_text() for folder in ("prd", "design")]
        criteria = [
            [" ".join(item.split()) for item in re.findall(r"- \*\*AC\d+:\*\* (.*?)(?=\n- \*\*AC|\n\n)", text, re.S)]
            for text in documents
        ]
        self.assertEqual(len(criteria[0]), 7)
        self.assertEqual(criteria[0], criteria[1])
        for folder in ("prd", "design"):
            self.assertIn("(0009-plugin-structure.md)", (root / folder / "README.md").read_text())
        self.assertIn("Codex is the primary", documents[0])
        self.assertIn("Codex-primary", documents[1])
