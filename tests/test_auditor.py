import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.extractor import Extractor
from core.validator import Validator
from main import generate_report


class ExtractorTests(unittest.TestCase):
    def test_extract_flattens_jsonld_arrays_and_graphs(self):
        html = """
        <html>
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@graph": [
                        {"@type": "Organization", "name": "Acme", "url": "https://example.com"},
                        {"@type": "Product", "name": "Widget", "description": "Useful", "offers": {"price": "10"}}
                    ]
                }
            </script>
            <script type="application/ld+json; charset=utf-8">
                [
                    {"@type": "schema:Article", "headline": "News", "datePublished": "2026-05-17", "author": "Team"},
                    {"@type": "https://schema.org/BreadcrumbList", "itemListElement": [{"position": 1}]}
                ]
            </script>
        </html>
        """

        schemas = Extractor.extract(html)

        self.assertEqual(len(schemas), 4)
        self.assertEqual(len(Extractor.filter_by_type(schemas, "Organization")), 1)
        self.assertEqual(len(Extractor.filter_by_type(schemas, "Product")), 1)
        self.assertEqual(len(Extractor.filter_by_type(schemas, "Article")), 1)
        self.assertEqual(len(Extractor.filter_by_type(schemas, "BreadcrumbList")), 1)

    def test_extract_skips_empty_and_invalid_scripts(self):
        html = """
        <script type="application/ld+json"></script>
        <script type="application/ld+json">{bad json}</script>
        <script type="application/json">{"@type": "Organization"}</script>
        """

        with redirect_stdout(io.StringIO()):
            self.assertEqual(Extractor.extract(html), [])


class ValidatorTests(unittest.TestCase):
    def test_validate_treats_empty_values_as_missing(self):
        schema = {"@type": "Organization", "name": "   ", "url": None}

        is_valid, missing_fields = Validator.validate(schema, "Organization")

        self.assertFalse(is_valid)
        self.assertEqual(missing_fields, ["name", "url"])

    def test_validate_accepts_nested_paths_inside_lists(self):
        schema = {"offers": [{"price": ""}, {"price": "19.99"}]}

        self.assertTrue(Validator._has_present_value(schema, "offers.price"))


class ReportTests(unittest.TestCase):
    def test_generate_report_writes_one_row_per_schema_type(self):
        audit_results = [
            {
                "url": "https://example.com",
                "status": "success",
                "found_schemas": 2,
                "validations": {
                    "Organization": {
                        "status": "valid",
                        "total": 1,
                        "valid": 1,
                        "invalid": 0,
                        "issues": [],
                    },
                    "Product": {"status": "not_found"},
                },
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "audit_report.csv"
            with redirect_stdout(io.StringIO()):
                generate_report(audit_results, str(report_path))

            with open(report_path, newline="", encoding="utf-8") as report_file:
                rows = list(csv.DictReader(report_file))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Schema Type"], "Organization")
        self.assertEqual(rows[0]["Type Status"], "valid")
        self.assertEqual(rows[1]["Schema Type"], "Product")
        self.assertEqual(rows[1]["Type Status"], "not_found")


if __name__ == "__main__":
    unittest.main()
