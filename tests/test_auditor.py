import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from core.extractor import Extractor, extract_json_ld, extract_microdata, extract_schema_markup
from core.validator import (
    PAGE_EXPECTATIONS,
    SCHEMA_STANDARDS,
    Validator,
    audit_page_completeness,
    audit_schema,
    deep_audit,
)
from main import USER_AGENT, _infer_page_type, run_audit


class ExtractorTests(unittest.TestCase):
    def test_extract_json_ld_returns_flat_schema_objects(self):
        html = """
        <script type="application/ld+json">
            {"@type": "Organization", "name": "Acme", "url": "https://example.com"}
        </script>
        <script type="application/ld+json">
            [
                {"@type": "Product", "name": "Widget"},
                {"@graph": [{"@type": "Article", "headline": "News"}]}
            ]
        </script>
        """

        schemas = extract_json_ld(html)

        self.assertEqual(len(schemas), 3)
        self.assertEqual([schema["@type"] for schema in schemas], ["Organization", "Product", "Article"])

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

    def test_extract_microdata_finds_schema_org_organization(self):
        html = """
        <link rel="canonical" href="https://triprindia.com/">
        <h1 itemscope itemtype="http://schema.org/Organization">
            <a itemprop="url" href="/">
                <span>TRIPR</span>
                <img itemprop="logo" src="//triprindia.com/logo.png" />
            </a>
        </h1>
        """

        schemas = extract_microdata(html)

        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["@type"], "Organization")
        self.assertEqual(schemas[0]["name"], "TRIPR")
        self.assertEqual(schemas[0]["url"], "https://triprindia.com/")
        self.assertEqual(schemas[0]["logo"], "https://triprindia.com/logo.png")

    def test_extract_schema_markup_combines_json_ld_and_microdata(self):
        html = """
        <script type="application/ld+json">
            {"@context": "https://schema.org", "@type": "ProductGroup", "name": "Trips", "productGroupID": "TRIPS"}
        </script>
        <div itemscope itemtype="https://schema.org/Organization">
            <meta itemprop="name" content="TRIPR">
            <link itemprop="url" href="https://triprindia.com/">
        </div>
        """

        schemas = extract_schema_markup(html)

        self.assertEqual([schema["@type"] for schema in schemas], ["ProductGroup", "Organization"])

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


class SchemaStandardAuditTests(unittest.TestCase):
    def test_schema_standards_include_core_types_and_primitive_types(self):
        self.assertIn("FAQPage", SCHEMA_STANDARDS)
        self.assertIn("Question", SCHEMA_STANDARDS)
        self.assertIn("Answer", SCHEMA_STANDARDS)
        self.assertIn("Brand", SCHEMA_STANDARDS)
        self.assertIn("ImageObject", SCHEMA_STANDARDS)
        self.assertIn("ContactPoint", SCHEMA_STANDARDS)
        self.assertIn("SearchAction", SCHEMA_STANDARDS)
        self.assertIn("ProductGroup", SCHEMA_STANDARDS)
        self.assertIn("Organization", SCHEMA_STANDARDS)
        self.assertIn("Product", SCHEMA_STANDARDS)
        self.assertIn("Offer", SCHEMA_STANDARDS)
        self.assertIn("Article", SCHEMA_STANDARDS)
        self.assertIn("CollectionPage", SCHEMA_STANDARDS)
        self.assertIn("LocalBusiness", SCHEMA_STANDARDS)
        self.assertIs(SCHEMA_STANDARDS["ProductGroup"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Organization"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Product"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Offer"]["types"]["price"], float)
        self.assertIs(SCHEMA_STANDARDS["Answer"]["types"]["text"], str)
        self.assertIs(SCHEMA_STANDARDS["ImageObject"]["types"]["contentUrl"], str)
        self.assertIs(SCHEMA_STANDARDS["ContactPoint"]["types"]["telephone"], str)
        self.assertIs(SCHEMA_STANDARDS["SearchAction"]["types"]["target"], str)

    def test_contact_point_requires_telephone_and_contact_type(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "ContactPoint",
            "telephone": "+91-0000000000",
            "contactType": "customer support",
            "email": "support@example.com",
        }
        missing_contact_type_schema = {
            "@context": "https://schema.org",
            "@type": "ContactPoint",
            "telephone": "+91-0000000000",
        }

        valid_rows = deep_audit(valid_schema)
        missing_contact_type_rows = deep_audit(missing_contact_type_schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in valid_rows))
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "contactType"
                for row in missing_contact_type_rows
            )
        )

    def test_search_action_requires_target(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "SearchAction",
            "target": "https://example.com/search?q={search_term_string}",
            "query-input": "required name=search_term_string",
        }
        missing_target_schema = {
            "@context": "https://schema.org",
            "@type": "SearchAction",
            "query-input": "required name=search_term_string",
        }

        valid_rows = deep_audit(valid_schema)
        missing_target_rows = deep_audit(missing_target_schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in valid_rows))
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "target"
                for row in missing_target_rows
            )
        )

    def test_image_object_accepts_content_url_or_url(self):
        content_url_schema = {
            "@context": "https://schema.org",
            "@type": "ImageObject",
            "contentUrl": "https://example.com/collection.jpg",
            "caption": "T-shirt collection",
        }
        url_schema = {
            "@context": "https://schema.org",
            "@type": "ImageObject",
            "url": "https://example.com/collection.jpg",
            "caption": "T-shirt collection",
        }
        missing_source_schema = {
            "@context": "https://schema.org",
            "@type": "ImageObject",
            "caption": "T-shirt collection",
        }

        content_url_rows = deep_audit(content_url_schema)
        url_rows = deep_audit(url_schema)
        missing_source_rows = deep_audit(missing_source_schema)

        self.assertFalse(any(row["severity"] == "Critical Error" for row in content_url_rows))
        self.assertFalse(any(row["severity"] == "Critical Error" for row in url_rows))
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "contentUrl or url"
                for row in missing_source_rows
            )
        )

    def test_collection_page_schema_requires_name(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "T-shirts",
            "description": "A collection of Tripr t-shirts.",
            "url": "https://example.com/collections/t-shirts",
        }
        missing_name_schema = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "url": "https://example.com/collections/t-shirts",
        }

        valid_rows = deep_audit(valid_schema)
        missing_name_rows = deep_audit(missing_name_schema)

        self.assertEqual(valid_rows[0]["schema_type"], "CollectionPage")
        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "name"
                for row in missing_name_rows
            )
        )

    def test_faq_page_recurses_into_questions_and_answers(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "What is Tripr?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Tripr sells travel-inspired clothing.",
                    },
                }
            ],
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["severity"] == "Critical Error" for row in rows))
        self.assertTrue(
            any(
                row["schema_path"] == "$.mainEntity[0].acceptedAnswer"
                and row["schema_type"] == "Answer"
                and row["severity"] == "Valid"
                for row in rows
            )
        )

    def test_faq_page_flags_missing_answer_text(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "What is Tripr?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                    },
                }
            ],
        }

        rows = deep_audit(schema)

        self.assertTrue(
            any(
                row["schema_type"] == "Answer"
                and row["severity"] == "Critical Error"
                and row["property"] == "text"
                for row in rows
            )
        )

    def test_brand_schema_requires_only_name(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Brand",
            "name": "Tripr",
        }

        rows = deep_audit(schema)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema_type"], "Brand")
        self.assertEqual(rows[0]["severity"], "Valid")

    def test_product_group_accepts_product_group_id_without_unknown_warning(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Trip package variations",
            "productGroupID": "TRIP-GROUP-001",
            "description": "Trip packages with options.",
            "url": "https://example.com/trips",
            "variesBy": "https://schema.org/size",
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in rows))
        self.assertEqual(rows[0]["schema_type"], "ProductGroup")
        self.assertEqual(rows[0]["severity"], "Valid")

    def test_product_group_recurses_into_has_variant_array(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Trip package variations",
            "description": "Trip packages with options.",
            "url": "https://example.com/trips",
            "variesBy": ["destination", "duration"],
            "hasVariant": [
                {
                    "@type": "Product",
                    "name": "Goa weekend",
                    "description": "Weekend Goa package.",
                    "image": "https://example.com/goa.jpg",
                    "brand": "Tripr",
                    "offers": {
                        "@type": "Offer",
                        "price": "4999",
                        "priceCurrency": "INR",
                        "availability": "https://schema.org/InStock",
                        "url": "https://example.com/goa",
                        "itemCondition": "https://schema.org/NewCondition",
                        "seller": "Tripr",
                        "priceValidUntil": "2026-12-31",
                    },
                }
            ],
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["severity"] == "Critical Error" for row in rows))
        self.assertTrue(any(row["schema_path"] == "$.hasVariant[0]" for row in rows))
        self.assertTrue(any(row["schema_path"] == "$.hasVariant[0].offers" for row in rows))

    def test_product_group_requires_has_variant_or_product_group_id(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Trip package variations",
            "description": "Trip packages with options.",
            "url": "https://example.com/trips",
            "variesBy": "destination",
        }

        rows = deep_audit(schema)

        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "hasVariant or productGroupID"
                for row in rows
            )
        )

    def test_deep_audit_recurses_into_nested_offer(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Trip package",
            "description": "A curated trip package.",
            "image": "https://example.com/image.jpg",
            "sku": "TRIP-001",
            "brand": "Tripr",
            "offers": {
                "@type": "Offer",
                "price": "199.99",
            },
        }

        rows = deep_audit(schema)
        critical_fields = {
            row["property"]
            for row in rows
            if row["severity"] == "Critical Error" and row["schema_type"] == "Offer"
        }

        self.assertEqual(critical_fields, {"priceCurrency", "availability"})

    def test_deep_audit_flags_invalid_context(self):
        schema = {
            "@context": "https://example.com",
            "@type": "Article",
            "headline": "Schema news",
            "datePublished": "2026-05-17",
            "author": "Editorial Team",
            "dateModified": "2026-05-17",
            "image": "https://example.com/news.jpg",
            "publisher": "Example",
            "description": "A schema update.",
        }

        rows = deep_audit(schema)

        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["issue_type"] == "Invalid Context"
                for row in rows
            )
        )

    def test_deep_audit_flags_invalid_primitive_type(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Offer",
            "price": "free",
            "priceCurrency": "INR",
            "availability": "https://schema.org/InStock",
            "url": "https://example.com",
            "itemCondition": "https://schema.org/NewCondition",
            "seller": "Tripr",
            "priceValidUntil": "2026-12-31",
        }

        rows = deep_audit(schema)

        self.assertTrue(
            any(
                row["issue_type"] == "Invalid Property Type"
                and row["property"] == "price"
                and row["severity"] == "Critical Error"
                for row in rows
            )
        )

    def test_audit_schema_handles_graph_arrays_for_pandas_rows(self):
        schemas = [
            {
                "@context": {"@vocab": "https://schema.org/"},
                "@graph": [
                    {
                        "@type": "LocalBusiness",
                        "name": "Tripr",
                        "address": "Kochi, Kerala",
                        "telephone": "+91-0000000000",
                        "url": "https://triprindia.com",
                        "image": "https://triprindia.com/logo.png",
                        "priceRange": "$$",
                        "openingHours": "Mo-Sa 09:00-18:00",
                        "geo": {"latitude": 9.9312, "longitude": 76.2673},
                    }
                ],
            }
        ]

        rows = audit_schema(schemas)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema_type"], "LocalBusiness")
        self.assertEqual(rows[0]["severity"], "Valid")
        self.assertEqual(rows[0]["schema_path"], "$[0].@graph[0]")

    def test_page_expectations_define_required_schema_types(self):
        self.assertEqual(PAGE_EXPECTATIONS["homepage"], ["Organization", "WebSite"])
        self.assertEqual(PAGE_EXPECTATIONS["product"], ["Product", "Offer"])
        self.assertEqual(PAGE_EXPECTATIONS["collection"], ["ItemList", "BreadcrumbList"])

    def test_audit_page_completeness_flags_missing_schema_blocks(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "Tripr",
                "url": "https://triprindia.com",
            }
        ]

        rows = audit_page_completeness("homepage", schemas)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "Critical Error")
        self.assertEqual(rows[0]["issue_type"], "Missing Required Schema")
        self.assertEqual(rows[0]["schema_type"], "WebSite")

    def test_audit_page_completeness_finds_nested_required_types(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Trip package",
                "offers": {
                    "@type": "Offer",
                    "price": "199.99",
                    "priceCurrency": "INR",
                    "availability": "https://schema.org/InStock",
                },
            }
        ]

        self.assertEqual(audit_page_completeness("product", schemas), [])

    def test_audit_schema_can_include_page_completeness_rows(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "Tripr",
                "url": "https://triprindia.com",
            }
        ]

        rows = audit_schema(schemas, page_type="homepage")

        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["issue_type"] == "Missing Required Schema"
                and row["schema_type"] == "WebSite"
                for row in rows
            )
        )

    def test_homepage_groups_product_variant_warnings(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "Tripr",
                "url": "https://triprindia.com",
                "logo": "https://triprindia.com/logo.png",
                "sameAs": ["https://instagram.com/triprindia"],
                "description": "Tripr India.",
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "Tripr",
                "url": "https://triprindia.com",
                "potentialAction": {"@type": "SearchAction"},
            },
            {
                "@context": "https://schema.org",
                "@type": "ProductGroup",
                "name": "Trip variations",
                "hasVariant": [
                    {
                        "@type": "Product",
                        "name": "Goa weekend",
                        "offers": {
                            "@type": "Offer",
                            "price": "4999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                        },
                    },
                    {
                        "@type": "Product",
                        "name": "Munnar weekend",
                        "offers": {
                            "@type": "Offer",
                            "price": "5999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                        },
                    },
                ],
            },
        ]

        rows = audit_schema(schemas, page_type="homepage")

        summary_rows = [
            row
            for row in rows
            if row["issue_type"] == "Grouped Homepage Product Variant Warnings"
        ]
        individual_variant_warnings = [
            row
            for row in rows
            if row["severity"] == "Warning"
            and row["schema_type"] in {"ProductGroup", "Product", "Offer"}
        ]

        self.assertEqual(len(summary_rows), 1)
        self.assertEqual(individual_variant_warnings, [])
        self.assertIn("2 product variants", summary_rows[0]["message"])

    def test_product_page_groups_identical_variant_warnings_by_property(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "ProductGroup",
                "name": "Trip variations",
                "description": "Trip variations.",
                "url": "https://example.com/products/trips",
                "variesBy": "size",
                "hasVariant": [
                    {
                        "@type": "Product",
                        "name": "Small trip tee",
                        "description": "Small tee.",
                        "image": "https://example.com/small.jpg",
                        "sku": "TRIP-S",
                        "brand": "Tripr",
                        "offers": {
                            "@type": "Offer",
                            "price": "999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                            "url": "https://example.com/products/trips?variant=s",
                            "seller": "Tripr",
                        },
                    },
                    {
                        "@type": "Product",
                        "name": "Large trip tee",
                        "description": "Large tee.",
                        "image": "https://example.com/large.jpg",
                        "sku": "TRIP-L",
                        "brand": "Tripr",
                        "offers": {
                            "@type": "Offer",
                            "price": "999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                            "url": "https://example.com/products/trips?variant=l",
                            "seller": "Tripr",
                        },
                    },
                ],
            }
        ]

        rows = audit_schema(schemas, page_type="product")
        grouped_rows = [
            row
            for row in rows
            if row["issue_type"] == "Grouped Product Variant Warning"
        ]
        individual_price_valid_until_rows = [
            row
            for row in rows
            if row["property"] == "priceValidUntil"
            and row["issue_type"] == "Missing Recommended Property"
        ]

        self.assertEqual(len(grouped_rows), 2)
        self.assertEqual(
            {row["property"] for row in grouped_rows},
            {"itemCondition", "priceValidUntil"},
        )
        self.assertEqual(individual_price_valid_until_rows, [])
        self.assertTrue(
            all("all 2 product variant variations" in row["message"] for row in grouped_rows)
        )


class OrchestrationTests(unittest.TestCase):
    def test_run_audit_fetches_extracts_validates_and_writes_csv(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Trip package",
                    "offers": {
                        "@type": "Offer",
                        "price": "199.99",
                        "priceCurrency": "INR",
                        "availability": "https://schema.org/InStock"
                    }
                }
            </script>
            <h1 itemscope itemtype="http://schema.org/Organization">
                <a itemprop="url" href="https://example.com/">
                    <span itemprop="name">Example</span>
                </a>
            </h1>
            """

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.requests.get", return_value=FakeResponse()) as request_mock:
                    with redirect_stdout(io.StringIO()):
                        report_data = run_audit("example.com")

            report_path = Path(tmpdir) / "example.com_schema_audit.csv"

            self.assertTrue(report_path.exists())

        request_mock.assert_called_once()
        self.assertEqual(request_mock.call_args.kwargs["headers"]["User-Agent"], USER_AGENT)
        self.assertIn("url", report_data.columns)
        self.assertIn("severity", report_data.columns)
        self.assertIn("Organization", set(report_data["schema_type"]))
        self.assertGreaterEqual(len(report_data), 1)

    def test_infer_page_type_from_url_path(self):
        self.assertEqual(_infer_page_type("https://triprindia.com"), "homepage")
        self.assertEqual(_infer_page_type("https://triprindia.com/"), "homepage")
        self.assertEqual(
            _infer_page_type("https://triprindia.com/products/black-tshirt"),
            "product",
        )
        self.assertEqual(
            _infer_page_type("https://triprindia.com/collections/tshirts"),
            "collection",
        )


if __name__ == "__main__":
    unittest.main()
