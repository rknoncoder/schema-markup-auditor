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
    MAJOR_STATUS_SCHEMA_TYPES,
)
from main import USER_AGENT, _infer_page_type, extract_storefront_node, run_audit


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

    def test_extract_json_ld_passes_graph_context_to_flattened_nodes(self):
        html = """
        <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "Organization", "name": "Acme", "url": "https://example.com"},
                    {"@type": "WebSite", "name": "Acme", "url": "https://example.com"}
                ]
            }
        </script>
        """

        schemas = extract_json_ld(html)

        self.assertEqual([schema["@type"] for schema in schemas], ["Organization", "WebSite"])
        self.assertTrue(all(schema.get("@context") == "https://schema.org" for schema in schemas))

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
        self.assertIn("AggregateRating", SCHEMA_STANDARDS)
        self.assertIn("ImageObject", SCHEMA_STANDARDS)
        self.assertIn("ContactPoint", SCHEMA_STANDARDS)
        self.assertIn("SearchAction", SCHEMA_STANDARDS)
        self.assertIn("ReadAction", SCHEMA_STANDARDS)
        self.assertIn("WebPage", SCHEMA_STANDARDS)
        self.assertIn("ListItem", SCHEMA_STANDARDS)
        self.assertIn("EntryPoint", SCHEMA_STANDARDS)
        self.assertIn("PropertyValueSpecification", SCHEMA_STANDARDS)
        self.assertIn("PropertyValue", SCHEMA_STANDARDS)
        self.assertIn("ProductGroup", SCHEMA_STANDARDS)
        self.assertIn("Organization", SCHEMA_STANDARDS)
        self.assertIn("Product", SCHEMA_STANDARDS)
        self.assertIn("Offer", SCHEMA_STANDARDS)
        self.assertIn("AggregateOffer", SCHEMA_STANDARDS)
        self.assertIn("Article", SCHEMA_STANDARDS)
        self.assertIn("CollectionPage", SCHEMA_STANDARDS)
        self.assertIn("LocalBusiness", SCHEMA_STANDARDS)
        self.assertIs(SCHEMA_STANDARDS["ProductGroup"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Organization"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Product"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["Offer"]["types"]["price"], float)
        self.assertEqual(SCHEMA_STANDARDS["AggregateOffer"]["types"]["lowPrice"], (str, int, float))
        self.assertIs(SCHEMA_STANDARDS["Answer"]["types"]["text"], str)
        self.assertEqual(SCHEMA_STANDARDS["AggregateRating"]["types"]["ratingValue"], (str, int, float))
        self.assertIs(SCHEMA_STANDARDS["ImageObject"]["types"]["contentUrl"], str)
        self.assertIs(SCHEMA_STANDARDS["ContactPoint"]["types"]["telephone"], str)
        self.assertEqual(SCHEMA_STANDARDS["SearchAction"]["types"]["target"], (str, dict))
        self.assertIs(SCHEMA_STANDARDS["WebPage"]["types"]["name"], str)
        self.assertIs(SCHEMA_STANDARDS["ListItem"]["types"]["position"], int)
        self.assertIs(SCHEMA_STANDARDS["EntryPoint"]["types"]["urlTemplate"], str)
        self.assertIs(SCHEMA_STANDARDS["PropertyValueSpecification"]["types"]["valueName"], str)
        self.assertIs(SCHEMA_STANDARDS["PropertyValue"]["types"]["name"], str)

    def test_read_action_accepts_flexible_target_shapes(self):
        string_target_schema = {
            "@context": "https://schema.org",
            "@type": "ReadAction",
            "target": "https://example.com/blog/how-to-audit-schema",
        }
        list_target_schema = {
            "@context": "https://schema.org",
            "@type": "ReadAction",
            "target": ["https://example.com/blog/how-to-audit-schema"],
        }
        dict_target_schema = {
            "@context": "https://schema.org",
            "@type": "ReadAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": "https://example.com/blog/how-to-audit-schema",
            },
        }
        missing_target_schema = {
            "@context": "https://schema.org",
            "@type": "ReadAction",
        }

        string_target_rows = deep_audit(string_target_schema)
        list_target_rows = deep_audit(list_target_schema)
        dict_target_rows = deep_audit(dict_target_schema)
        missing_target_rows = deep_audit(missing_target_schema)

        self.assertFalse(any(row["severity"] == "Critical Error" for row in string_target_rows))
        self.assertFalse(any(row["severity"] == "Critical Error" for row in list_target_rows))
        self.assertFalse(any(row["severity"] == "Critical Error" for row in dict_target_rows))
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "target"
                for row in missing_target_rows
            )
        )

    def test_web_page_requires_name(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "About us",
            "description": "Agency about page.",
            "url": "https://example.com/about",
        }
        missing_name_schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "url": "https://example.com/about",
        }

        valid_rows = deep_audit(valid_schema)
        missing_name_rows = deep_audit(missing_name_schema)

        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "name"
                for row in missing_name_rows
            )
        )

    def test_yoast_style_global_mapping_properties_are_allowed(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "About us",
            "description": "Agency about page.",
            "url": "https://example.com/about",
            "isPartOf": {
                "@type": "WebSite",
                "name": "Example",
                "url": "https://example.com",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": "https://example.com/search?q={search_term_string}",
                    "query-input": "required name=search_term_string",
                },
            },
            "publisher": {
                "@type": "Organization",
                "name": "Example",
                "url": "https://example.com",
                "logo": "https://example.com/logo.svg",
                "sameAs": ["https://www.linkedin.com/company/example"],
                "description": "Example organization.",
            },
            "inLanguage": "en-US",
            "primaryImageOfPage": {
                "@type": "ImageObject",
                "url": "https://example.com/about.jpg",
                "caption": "About Example",
                "height": 800,
                "width": 1200,
            },
            "thumbnailUrl": "https://example.com/about-thumb.jpg",
            "datePublished": "2026-05-01",
            "dateModified": "2026-05-27",
        }

        rows = deep_audit(schema)

        self.assertFalse(
            any(
                row["issue_type"] == "Unrecognized Property"
                and row["property"] in {
                    "dateModified",
                    "datePublished",
                    "inLanguage",
                    "isPartOf",
                    "primaryImageOfPage",
                    "publisher",
                    "thumbnailUrl",
                }
                for row in rows
            )
        )

    def test_open_world_unknown_properties_pass_silently(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "Flexible schema page",
            "description": "A page with future Schema.org and custom platform fields.",
            "url": "https://example.com/flexible-schema",
            "speakable": {
                "@type": "SpeakableSpecification",
                "cssSelector": [".headline", ".summary"],
            },
            "customShopifyField": {
                "themeSection": "hero",
                "enabled": True,
            },
            "futureSchemaOrgProperty": "Allowed by open-world validation.",
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["issue_type"] == "Unrecognized Property" for row in rows))

    def test_list_item_requires_position_and_item(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "ListItem",
            "position": 1,
            "item": "https://example.com/services",
            "name": "Services",
        }
        missing_item_schema = {
            "@context": "https://schema.org",
            "@type": "ListItem",
            "position": 1,
        }

        valid_rows = deep_audit(valid_schema)
        missing_item_rows = deep_audit(missing_item_schema)

        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "item"
                for row in missing_item_rows
            )
        )

    def test_list_item_accepts_numeric_string_position(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "ListItem",
            "position": "1",
            "item": "https://example.com/services",
            "name": "Services",
        }

        rows = deep_audit(schema)

        self.assertEqual(schema["position"], 1)
        self.assertFalse(
            any(
                row["issue_type"] == "Invalid Property Type"
                and row["property"] == "position"
                for row in rows
            )
        )
        self.assertEqual(rows[0]["severity"], "Valid")

    def test_entry_point_requires_url_template(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "EntryPoint",
            "urlTemplate": "https://example.com/search?q={search_term_string}",
        }
        missing_url_template_schema = {
            "@context": "https://schema.org",
            "@type": "EntryPoint",
        }

        valid_rows = deep_audit(valid_schema)
        missing_url_template_rows = deep_audit(missing_url_template_schema)

        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "urlTemplate"
                for row in missing_url_template_rows
            )
        )

    def test_property_value_specification_requires_value_name(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "PropertyValueSpecification",
            "valueName": "search_term_string",
        }
        missing_value_name_schema = {
            "@context": "https://schema.org",
            "@type": "PropertyValueSpecification",
        }

        valid_rows = deep_audit(valid_schema)
        missing_value_name_rows = deep_audit(missing_value_name_schema)

        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "valueName"
                for row in missing_value_name_rows
            )
        )

    def test_property_value_requires_name_and_value(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "PropertyValue",
            "name": "Material",
            "value": "Cotton",
        }
        missing_value_schema = {
            "@context": "https://schema.org",
            "@type": "PropertyValue",
            "name": "Material",
        }

        valid_rows = deep_audit(valid_schema)
        missing_value_rows = deep_audit(missing_value_schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in valid_rows))
        self.assertEqual(valid_rows[0]["severity"], "Valid")
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "value"
                for row in missing_value_rows
            )
        )

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

    def test_search_action_accepts_nested_target_and_query_input(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": "https://example.com/search?q={search_term_string}",
            },
            "query-input": {
                "@type": "PropertyValueSpecification",
                "valueName": "search_term_string",
            },
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["severity"] == "Critical Error" for row in rows))
        self.assertTrue(any(row["schema_type"] == "EntryPoint" for row in rows))
        self.assertTrue(
            any(row["schema_type"] == "PropertyValueSpecification" for row in rows)
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

    def test_aggregate_rating_accepts_review_count_or_rating_count(self):
        review_count_schema = {
            "@context": "https://schema.org",
            "@type": "AggregateRating",
            "ratingValue": "4.6",
            "reviewCount": "1,245",
            "bestRating": 5,
            "worstRating": 1,
        }
        rating_count_schema = {
            "@context": "https://schema.org",
            "@type": "AggregateRating",
            "ratingValue": 4.6,
            "ratingCount": 1245,
            "bestRating": "5",
            "worstRating": "1",
        }

        review_count_rows = deep_audit(review_count_schema)
        rating_count_rows = deep_audit(rating_count_schema)

        self.assertFalse(
            any(row["issue_type"] == "Unsupported Schema Type" for row in review_count_rows)
        )
        self.assertFalse(any(row["severity"] == "Critical Error" for row in review_count_rows))
        self.assertFalse(any(row["severity"] == "Critical Error" for row in rating_count_rows))

    def test_aggregate_rating_requires_review_count_or_rating_count(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "AggregateRating",
            "ratingValue": 4.6,
            "bestRating": 5,
            "worstRating": 1,
        }

        rows = deep_audit(schema)

        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "reviewCount or ratingCount"
                for row in rows
            )
        )

    def test_product_recurses_into_aggregate_rating(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Nobero tee",
            "description": "A product with rating markup.",
            "image": "https://example.com/tee.jpg",
            "sku": "TEE-001",
            "brand": "Nobero",
            "offers": {
                "@type": "Offer",
                "price": "999",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock",
                "url": "https://example.com/products/tee",
                "itemCondition": "https://schema.org/NewCondition",
                "seller": "Nobero",
                "priceValidUntil": "2026-12-31",
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "4.8",
                "ratingCount": "240",
                "bestRating": "5",
                "worstRating": "1",
            },
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in rows))
        self.assertTrue(
            any(
                row["schema_type"] == "AggregateRating"
                and row["severity"] == "Valid"
                for row in rows
            )
        )

    def test_aggregate_offer_requires_low_price_and_currency(self):
        valid_schema = {
            "@context": "https://schema.org",
            "@type": "AggregateOffer",
            "lowPrice": "499",
            "priceCurrency": "INR",
            "highPrice": 999,
            "offerCount": "8",
        }
        missing_low_price_schema = {
            "@context": "https://schema.org",
            "@type": "AggregateOffer",
            "priceCurrency": "INR",
        }

        valid_rows = deep_audit(valid_schema)
        missing_low_price_rows = deep_audit(missing_low_price_schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in valid_rows))
        self.assertFalse(any(row["severity"] == "Critical Error" for row in valid_rows))
        self.assertTrue(
            any(
                row["severity"] == "Critical Error"
                and row["property"] == "lowPrice"
                for row in missing_low_price_rows
            )
        )

    def test_product_accepts_aggregate_offer_as_pricing_schema(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Aggregate priced tee",
                "description": "A product with aggregate pricing.",
                "image": "https://example.com/tee.jpg",
                "sku": "TEE-AGG",
                "brand": "Example",
                "offers": {
                    "@type": "AggregateOffer",
                    "lowPrice": "499",
                    "priceCurrency": "INR",
                    "highPrice": "999",
                    "offerCount": 8,
                },
            }
        ]

        completeness_rows = audit_page_completeness("product", schemas)
        audit_rows = audit_schema(schemas, page_type="product")

        self.assertEqual(completeness_rows, [])
        self.assertFalse(
            any(
                row["issue_type"] == "Missing Required Schema"
                and row["schema_type"] == "Offer or AggregateOffer"
                for row in audit_rows
            )
        )
        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in audit_rows))

    def test_product_flags_misplaced_root_pricing_property(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Snitch shirt",
                "description": "A product with misplaced pricing data.",
                "image": "https://example.com/shirt.jpg",
                "sku": "SHIRT-ROOT",
                "brand": "Snitch",
                "highPrice": "1999",
                "offers": {
                    "@type": "Offer",
                    "price": "999",
                    "priceCurrency": "INR",
                    "availability": "https://schema.org/InStock",
                    "url": "https://example.com/products/shirt",
                    "itemCondition": "https://schema.org/NewCondition",
                    "seller": "Snitch",
                    "priceValidUntil": "2026-12-31",
                },
            }
        ]

        rows = audit_schema(schemas, page_type="product")
        deep_rows = deep_audit(schemas[0])

        self.assertTrue(
            any(
                row["schema_path"] == "$[0]"
                and row["schema_type"] == "Product"
                and row["severity"] == "Critical Error"
                and row["issue_type"] == "Invalid Property Placement"
                and row["property"] == "highPrice"
                for row in rows
            )
        )
        self.assertTrue(
            any(
                row["schema_path"] == "$"
                and row["schema_type"] == "Product"
                and row["severity"] == "Critical Error"
                and row["issue_type"] == "Invalid Property Placement"
                and row["property"] == "highPrice"
                for row in deep_rows
            )
        )

    def test_product_accepts_optional_merchandising_properties(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Snitch shirt",
            "description": "A shirt with fashion merchandising metadata.",
            "image": "https://example.com/shirt.jpg",
            "sku": "SHIRT-META",
            "brand": "Snitch",
            "url": "https://example.com/products/shirt",
            "productID": "gid://shopify/Product/123",
            "gtin": "0123456789012",
            "gtin8": 12345678,
            "gtin13": "1234567890123",
            "gtin14": 12345678901234,
            "mpn": "SHIRT-META-M",
            "category": "Shirts",
            "color": "Black",
            "material": "Cotton",
            "pattern": "Solid",
            "size": "M",
            "offers": {
                "@type": "Offer",
                "price": "999",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock",
                "url": "https://example.com/products/shirt",
                "itemCondition": "https://schema.org/NewCondition",
                "seller": "Snitch",
                "priceValidUntil": "2026-12-31",
            },
        }

        rows = deep_audit(schema)

        self.assertFalse(
            any(
                row["issue_type"] == "Unrecognized Property"
                and row["property"] in {
                    "category",
                    "color",
                    "gtin",
                    "gtin8",
                    "gtin13",
                    "gtin14",
                    "material",
                    "mpn",
                    "pattern",
                    "productID",
                    "size",
                }
                for row in rows
            )
        )

    def test_product_root_valid_row_stays_visible_with_nested_offer_issues(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Snitch shirt",
                "description": "A product shell with a child offer issue.",
                "image": "https://example.com/shirt.jpg",
                "sku": "SHIRT-SHELL",
                "brand": "Snitch",
                "offers": {
                    "@type": "Offer",
                    "price": "999",
                    "priceCurrency": "INR",
                    "availability": "https://schema.org/InStock",
                    "url": "https://example.com/products/shirt",
                    "itemCondition": "https://schema.org/NewCondition",
                    "seller": "Snitch",
                    "highPrice": "1999",
                },
            }
        ]

        rows = audit_schema(schemas, page_type="product")

        self.assertTrue(
            any(
                row["schema_path"] == "$[0]"
                and row["schema_type"] == "Product"
                and row["severity"] == "Valid"
                for row in rows
            )
        )
        self.assertTrue(
            any(
                row["schema_path"] == "$[0].offers"
                and row["severity"] == "Critical Error"
                and row["issue_type"] == "Invalid Property Placement"
                and row["property"] == "highPrice"
                for row in rows
            )
        )

    def test_major_status_schema_types_include_core_master_schemas(self):
        self.assertTrue(
            {
                "Article",
                "BreadcrumbList",
                "CollectionPage",
                "LocalBusiness",
                "Organization",
                "Product",
                "ProductGroup",
                "WebSite",
            }.issubset(MAJOR_STATUS_SCHEMA_TYPES)
        )

    def test_website_root_valid_row_stays_visible_with_search_action_child(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "ColourPop",
                "url": "https://colourpop.com/",
                "logo": "https://colourpop.com/logo.svg",
                "sameAs": ["https://www.instagram.com/colourpopcosmetics/"],
                "description": "Colour cosmetics brand.",
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "ColourPop",
                "url": "https://colourpop.com/",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": "https://colourpop.com/search?q={search_term_string}",
                    "query-input": "required name=search_term_string",
                },
            },
        ]

        rows = audit_schema(schemas, page_type="homepage")

        self.assertTrue(
            any(
                row["schema_path"] == "$[1]"
                and row["schema_type"] == "WebSite"
                and row["severity"] == "Valid"
                for row in rows
            )
        )
        self.assertTrue(
            any(
                row["schema_path"] == "$[1].potentialAction"
                and row["schema_type"] == "SearchAction"
                and row["severity"] == "Valid"
                for row in rows
            )
        )

    def test_product_group_accepts_optional_merchandising_properties(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Solid black shirts",
            "description": "A product group with fashion metadata.",
            "url": "https://example.com/products/solid-black-shirt",
            "productGroupID": "solid-black-shirt",
            "productID": "gid://shopify/ProductGroup/123",
            "category": "Shirts",
            "color": ["Black"],
            "material": "Cotton",
            "pattern": "Solid",
            "size": ["S", "M", "L"],
        }

        rows = deep_audit(schema)

        self.assertFalse(
            any(
                row["issue_type"] == "Unrecognized Property"
                and row["property"] in {"productID", "category", "color", "material", "pattern", "size"}
                for row in rows
            )
        )

    def test_product_group_root_valid_row_stays_visible_with_variant_issues(self):
        schemas = [
            {
                "@context": "https://schema.org",
                "@type": "ProductGroup",
                "name": "Solid black shirts",
                "description": "A clean product group shell with child variant issues.",
                "url": "https://example.com/products/solid-black-shirt",
                "variesBy": "size",
                "hasVariant": [
                    {
                        "@type": "Product",
                        "name": "Solid black shirt - M",
                        "description": "Medium solid black shirt.",
                        "image": "https://example.com/shirt.jpg",
                        "sku": "SHIRT-M",
                        "brand": "Snitch",
                        "offers": {
                            "@type": "Offer",
                            "price": "999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                        },
                    }
                ],
            }
        ]

        rows = audit_schema(schemas, page_type="product")

        self.assertTrue(
            any(
                row["schema_path"] == "$[0]"
                and row["schema_type"] == "ProductGroup"
                and row["severity"] == "Valid"
                for row in rows
            )
        )
        self.assertTrue(
            any(
                row["schema_path"].startswith("$[0].hasVariant")
                and row["severity"] in {"Warning", "Critical Error"}
                for row in rows
            )
        )

    def test_product_recurses_into_additional_property_values(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Snitch shirt",
            "description": "A shirt with additional product metadata.",
            "image": "https://example.com/shirt.jpg",
            "sku": "SHIRT-001",
            "brand": "Snitch",
            "offers": {
                "@type": "Offer",
                "price": "999",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock",
                "url": "https://example.com/products/shirt",
                "itemCondition": "https://schema.org/NewCondition",
                "seller": "Snitch",
                "priceValidUntil": "2026-12-31",
            },
            "additionalProperty": [
                {
                    "@type": "PropertyValue",
                    "name": "Fit",
                    "value": "Regular",
                },
                {
                    "@type": "PropertyValue",
                    "name": "Sleeve",
                    "value": "Full sleeve",
                },
                {
                    "@type": "PropertyValue",
                    "name": "Pattern",
                    "value": "Solid",
                },
            ],
        }

        rows = deep_audit(schema)

        self.assertFalse(any(row["issue_type"] == "Unsupported Schema Type" for row in rows))
        self.assertEqual(
            sum(row["schema_type"] == "PropertyValue" for row in rows),
            3,
        )

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

    def test_audit_schema_uses_inherited_context_for_nested_graph_blocks(self):
        html = """
        <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "WebSite",
                        "name": "Example",
                        "url": "https://example.com",
                        "potentialAction": {
                            "@type": "SearchAction",
                            "target": {
                                "@type": "EntryPoint",
                                "urlTemplate": "https://example.com/search?q={search_term_string}"
                            },
                            "query-input": {
                                "@type": "PropertyValueSpecification",
                                "valueName": "search_term_string"
                            }
                        }
                    }
                ]
            }
        </script>
        """

        rows = audit_schema(extract_json_ld(html))

        self.assertFalse(any(row["issue_type"] == "Invalid Context" for row in rows))
        self.assertTrue(any(row["schema_type"] == "EntryPoint" for row in rows))
        self.assertTrue(
            any(row["schema_type"] == "PropertyValueSpecification" for row in rows)
        )

    def test_page_expectations_define_required_schema_types(self):
        self.assertEqual(PAGE_EXPECTATIONS["homepage"], ["Organization", "WebSite"])
        self.assertEqual(PAGE_EXPECTATIONS["product"], ["Product", ("Offer", "AggregateOffer")])
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
    def test_extract_storefront_node_finds_nested_product_group(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "Nested Shopify product page",
            "mainEntity": {
                "@type": "ProductGroup",
                "name": "Nested tee variants",
                "hasVariant": [
                    {
                        "@type": "Product",
                        "name": "Nested tee small",
                        "offers": {
                            "@type": "Offer",
                            "price": "999",
                            "priceCurrency": "INR",
                            "availability": "https://schema.org/InStock",
                        },
                    }
                ],
            },
        }

        storefront_node = extract_storefront_node(schema)

        self.assertEqual(storefront_node["@type"], "ProductGroup")
        self.assertEqual(storefront_node["@context"], "https://schema.org")

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
                with patch("main.USE_HEADLESS_BROWSER", False):
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

    def test_run_audit_preserves_variant_query_string(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Variant tee",
                    "description": "A variant-specific product payload.",
                    "image": "https://example.com/tee.jpg",
                    "sku": "TEE-VARIANT",
                    "brand": "Nobero",
                    "offers": {
                        "@type": "Offer",
                        "price": "999",
                        "priceCurrency": "INR",
                        "availability": "https://schema.org/InStock",
                        "url": "https://example.com/products/tee?variant=37699714121894",
                        "itemCondition": "https://schema.org/NewCondition",
                        "seller": "Nobero",
                        "priceValidUntil": "2026-12-31"
                    }
                }
            </script>
            """

            def raise_for_status(self):
                return None

        target_url = "https://example.com/products/tee?variant=37699714121894"

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", False):
                    with patch("main.requests.get", return_value=FakeResponse()) as request_mock:
                        with redirect_stdout(io.StringIO()):
                            report_data = run_audit(target_url)

            report_path = (
                Path(tmpdir)
                / "example.com_products_tee_variant=37699714121894_schema_audit.csv"
            )

            self.assertTrue(report_path.exists())

        request_mock.assert_called_once()
        self.assertEqual(request_mock.call_args.args[0], target_url)
        self.assertTrue(all(report_data["url"] == target_url))

    def test_run_audit_keeps_root_schema_path_issue_rows(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Snitch shirt",
                    "description": "A product with misplaced pricing data.",
                    "image": "https://example.com/shirt.jpg",
                    "sku": "SHIRT-ROOT",
                    "brand": "Snitch",
                    "highPrice": "1999",
                    "offers": {
                        "@type": "Offer",
                        "price": "999",
                        "priceCurrency": "INR",
                        "availability": "https://schema.org/InStock",
                        "url": "https://example.com/products/shirt",
                        "itemCondition": "https://schema.org/NewCondition",
                        "seller": "Snitch",
                        "priceValidUntil": "2026-12-31"
                    }
                }
            </script>
            """

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", False):
                    with patch("main.requests.get", return_value=FakeResponse()):
                        with redirect_stdout(io.StringIO()):
                            report_data = run_audit("https://example.com/products/snitch-shirt")

            report_path = Path(tmpdir) / "example.com_products_snitch-shirt_schema_audit.csv"
            report_text = report_path.read_text(encoding="utf-8")

        root_issue_rows = report_data[
            (report_data["schema_path"] == "$[0]")
            & (report_data["schema_type"] == "Product")
            & (report_data["property"] == "highPrice")
        ]

        self.assertEqual(len(root_issue_rows), 1)
        self.assertEqual(root_issue_rows.iloc[0]["issue_type"], "Invalid Property Placement")
        self.assertIn("$[0],Product,Critical Error,Invalid Property Placement,highPrice", report_text)

    def test_run_audit_writes_executive_summary_before_csv_rows(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "name": "Summary Store",
                    "url": "https://example.com/about",
                    "logo": "https://example.com/logo.svg",
                    "sameAs": ["https://instagram.com/summarystore"],
                    "description": "A fully configured organization schema."
                }
            </script>
            """

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", False):
                    with patch("main.requests.get", return_value=FakeResponse()):
                        with redirect_stdout(io.StringIO()):
                            run_audit("https://example.com/about")

            report_path = Path(tmpdir) / "example.com_about_schema_audit.csv"
            report_text = report_path.read_text(encoding="utf-8")

        self.assertTrue(
            report_text.startswith(
                "# --------------------------------------------------\n"
                "# SCHEMA AUDIT EXECUTIVE SUMMARY\n"
                "# Total Schemas Detected: 1\n"
                "# Total Fully Valid Blocks: 1\n"
                "# Total Warnings Found: 0\n"
                "# Total Critical Errors Found: 0\n"
                "# --------------------------------------------------\n"
            )
        )
        self.assertIn("url,schema_path,schema_type,severity", report_text)

    def test_run_audit_uses_headless_crawler_when_enabled(self):
        rendered_html = """
        <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "Rendered Store",
                "url": "https://example.com",
                "logo": "https://example.com/logo.svg",
                "sameAs": ["https://instagram.com/renderedstore"],
                "description": "Schema injected after JavaScript rendering."
            }
        </script>
        """
        target_url = "https://example.com/products/rendered-tee?variant=123"

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", True):
                    with patch("main.Crawler") as crawler_mock:
                        with patch("main.requests.get") as request_mock:
                            crawler_instance = crawler_mock.return_value
                            crawler_instance.fetch.return_value = rendered_html

                            with redirect_stdout(io.StringIO()):
                                report_data = run_audit(target_url)

        crawler_mock.assert_called_once_with(
            timeout=30,
            use_playwright=True,
            max_retries=3,
        )
        crawler_instance.fetch.assert_called_once_with(target_url)
        request_mock.assert_not_called()
        self.assertIn("Organization", set(report_data["schema_type"]))
        self.assertTrue(all(report_data["url"] == target_url))

    def test_product_audit_keeps_root_organization_and_website_schemas(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "name": "Nobero",
                    "url": "https://nobero.com/",
                    "logo": "https://nobero.com/logo.svg",
                    "sameAs": ["https://instagram.com/noberodotcom"],
                    "description": "Pratyaya E-commerce"
                }
            </script>
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Nobero",
                    "url": "https://nobero.com/"
                }
            </script>
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Nobero tee",
                    "description": "A product page payload.",
                    "image": "https://nobero.com/tee.jpg",
                    "brand": "Nobero",
                    "offers": {
                        "@type": "Offer",
                        "price": "999",
                        "priceCurrency": "INR",
                        "availability": "https://schema.org/InStock",
                        "url": "https://nobero.com/products/tee",
                        "itemCondition": "https://schema.org/NewCondition",
                        "seller": "Nobero",
                        "priceValidUntil": "2026-12-31"
                    }
                }
            </script>
            """

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", False):
                    with patch("main.requests.get", return_value=FakeResponse()):
                        with redirect_stdout(io.StringIO()):
                            report_data = run_audit("https://nobero.com/products/tee")

        schema_types = set(report_data["schema_type"])

        self.assertIn("Organization", schema_types)
        self.assertIn("WebSite", schema_types)
        self.assertIn("Product", schema_types)

    def test_run_audit_groups_nested_storefront_variants_on_ambiguous_product_url(self):
        class FakeResponse:
            text = """
            <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": "Nested product landing page",
                    "mainEntity": {
                        "@type": "ProductGroup",
                        "name": "Trip tee variants",
                        "description": "Trip tee variations.",
                        "url": "https://example.com/pages/trip-tee",
                        "variesBy": "size",
                        "hasVariant": [
                            {
                                "@type": "Product",
                                "name": "Trip tee small",
                                "description": "Small tee.",
                                "image": "https://example.com/small.jpg",
                                "sku": "TRIP-S",
                                "brand": "Tripr",
                                "offers": {
                                    "@type": "Offer",
                                    "price": "999",
                                    "priceCurrency": "INR",
                                    "availability": "https://schema.org/InStock",
                                    "url": "https://example.com/pages/trip-tee?variant=s",
                                    "seller": "Tripr"
                                }
                            },
                            {
                                "@type": "Product",
                                "name": "Trip tee large",
                                "description": "Large tee.",
                                "image": "https://example.com/large.jpg",
                                "sku": "TRIP-L",
                                "brand": "Tripr",
                                "offers": {
                                    "@type": "Offer",
                                    "price": "999",
                                    "priceCurrency": "INR",
                                    "availability": "https://schema.org/InStock",
                                    "url": "https://example.com/pages/trip-tee?variant=l",
                                    "seller": "Tripr"
                                }
                            }
                        ]
                    }
                }
            </script>
            """

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.REPORTS_DIR", Path(tmpdir)):
                with patch("main.USE_HEADLESS_BROWSER", False):
                    with patch("main.requests.get", return_value=FakeResponse()):
                        with redirect_stdout(io.StringIO()):
                            report_data = run_audit("https://example.com/pages/trip-tee")

        grouped_rows = report_data[
            report_data["issue_type"] == "Grouped Product Variant Warning"
        ]

        self.assertEqual(set(grouped_rows["property"]), {"itemCondition", "priceValidUntil"})
        self.assertTrue(
            all(
                "all 2 product variant variations" in message
                for message in grouped_rows["message"]
            )
        )

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
        self.assertEqual(
            _infer_page_type(
                "https://example.com/pages/trip-tee",
                [
                    {
                        "@context": "https://schema.org",
                        "@type": "WebPage",
                        "about": {"@type": "Product", "name": "Trip tee"},
                    }
                ],
            ),
            "product",
        )


if __name__ == "__main__":
    unittest.main()
