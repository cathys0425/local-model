"""Offline checks for the frozen language-variation evaluation probe."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "part2"))

from rules import rules_extract
from evaluate_language_variation import extraction_exact
from language_cases import cases
from validation import validate_extraction


class LanguageVariationTests(unittest.TestCase):
    def test_rules_baseline_is_valid_but_not_exact_on_every_narrative(self):
        rows = []
        for case in cases():
            fields, _trace = rules_extract(None, case["invoice"], case["email"])
            errors = validate_extraction(fields, case["invoice"], case["email"])
            self.assertEqual(errors, [], case["id"])
            rows.append(extraction_exact(fields, case["gold"])[2])

        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(rows), 4)

    def test_case_set_has_distinct_invoice_references(self):
        rows = list(cases())
        invoice_numbers = [row["gold"]["invoice_number"] for row in rows]
        self.assertEqual(len(invoice_numbers), len(set(invoice_numbers)))
        self.assertTrue(all(row["gold"]["currency"] == "USD" for row in rows))


if __name__ == "__main__":
    unittest.main()