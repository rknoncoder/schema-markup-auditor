"""
Schema validation module.

Validates extracted schema fields against criteria.
"""

import re
from typing import Any, Dict, List, Tuple


SCHEMA_STANDARDS = {
    "FAQPage": {
        "required": ["mainEntity"],
        "recommended": [],
        "types": {
            "mainEntity": list,
        },
        "nested": {
            "mainEntity": "Question",
        },
    },
    "Question": {
        "required": ["name", "acceptedAnswer"],
        "recommended": [],
        "types": {
            "name": str,
            "acceptedAnswer": (dict, list),
        },
        "nested": {
            "acceptedAnswer": "Answer",
        },
    },
    "Answer": {
        "required": ["text"],
        "recommended": [],
        "types": {
            "text": str,
        },
        "nested": {},
    },
    "Brand": {
        "required": ["name"],
        "recommended": [],
        "types": {
            "name": str,
        },
        "nested": {},
    },
    "AggregateRating": {
        "required": ["ratingValue"],
        "required_any": [["reviewCount", "ratingCount"]],
        "recommended": ["bestRating", "worstRating"],
        "types": {
            "ratingValue": (str, int, float),
            "reviewCount": (str, int, float),
            "ratingCount": (str, int, float),
            "bestRating": (str, int, float),
            "worstRating": (str, int, float),
        },
        "nested": {},
    },
    "ImageObject": {
        "required": [],
        "required_any": [["contentUrl", "url"]],
        "recommended": ["caption", "height", "width"],
        "types": {
            "contentUrl": str,
            "url": str,
            "caption": str,
        },
        "nested": {},
    },
    "ContactPoint": {
        "required": ["telephone", "contactType"],
        "recommended": ["areaServed", "availableLanguage", "email"],
        "types": {
            "telephone": str,
            "contactType": str,
            "areaServed": (str, list),
            "availableLanguage": (str, list),
            "email": str,
            "contactOption": (str, list),
        },
        "nested": {},
    },
    "SearchAction": {
        "required": ["target"],
        "recommended": ["query-input"],
        "types": {
            "target": (str, dict),
            "query-input": (str, dict),
        },
        "nested": {},
    },
    "ReadAction": {
        "required": ["target"],
        "recommended": [],
        "types": {
            "target": (str, list, dict),
        },
        "nested": {},
    },
    "EntryPoint": {
        "required": ["urlTemplate"],
        "recommended": [],
        "types": {
            "urlTemplate": str,
        },
        "nested": {},
    },
    "PropertyValueSpecification": {
        "required": ["valueName"],
        "recommended": [],
        "types": {
            "valueName": str,
        },
        "nested": {},
    },
    "PropertyValue": {
        "required": ["name", "value"],
        "recommended": [],
        "types": {
            "name": str,
            "value": (str, int, float, bool),
        },
        "nested": {},
    },
    "WebSite": {
        "required": ["name", "url"],
        "recommended": ["potentialAction"],
        "types": {
            "name": str,
            "url": str,
            "potentialAction": (dict, list),
        },
        "nested": {},
    },
    "WebPage": {
        "required": ["name"],
        "recommended": ["description", "url"],
        "types": {
            "name": str,
            "description": str,
            "url": str,
            "about": (dict, list),
            "breadcrumb": (dict, list),
            "mainEntity": (dict, list),
        },
        "nested": {},
    },
    "Organization": {
        "required": ["name", "url"],
        "recommended": ["logo", "sameAs", "description"],
        "types": {
            "name": str,
            "url": str,
            "alternateName": str,
            "logo": (str, dict, list),
            "sameAs": (str, list),
            "description": str,
            "contactPoint": (dict, list),
        },
        "nested": {
            "contactPoint": "ContactPoint",
        },
    },
    "ProductGroup": {
        "required": ["name"],
        "required_any": [["hasVariant", "productGroupID"]],
        "recommended": ["description", "url", "variesBy"],
        "types": {
            "name": str,
            "hasVariant": (dict, list),
            "productGroupID": str,
            "productID": str,
            "category": (str, list),
            "color": (str, list),
            "material": (str, list),
            "pattern": (str, list),
            "size": (str, list),
            "description": str,
            "url": str,
            "variesBy": (str, list),
        },
        "nested": {
            "hasVariant": "Product",
        },
    },
    "Product": {
        "required": ["name", "offers"],
        "recommended": ["description", "image", "sku", "brand"],
        "types": {
            "name": str,
            "description": str,
            "image": (str, list),
            "sku": str,
            "brand": (str, dict),
            "url": str,
            "productID": str,
            "category": (str, list),
            "color": (str, list),
            "material": (str, list),
            "pattern": (str, list),
            "size": (str, list),
            "offers": (dict, list),
            "aggregateRating": dict,
            "additionalProperty": (dict, list),
        },
        "nested": {
            "offers": "Offer",
            "aggregateRating": "AggregateRating",
            "additionalProperty": "PropertyValue",
        },
    },
    "Offer": {
        "required": ["price", "priceCurrency", "availability"],
        "recommended": ["url", "itemCondition", "seller", "priceValidUntil"],
        "types": {
            "price": float,
            "priceCurrency": str,
            "availability": str,
            "url": str,
            "itemCondition": str,
            "seller": (str, dict),
            "priceValidUntil": str,
        },
        "nested": {},
    },
    "AggregateOffer": {
        "required": ["lowPrice", "priceCurrency"],
        "recommended": ["highPrice", "offerCount", "offers"],
        "types": {
            "lowPrice": (str, int, float),
            "priceCurrency": str,
            "highPrice": (str, int, float),
            "offerCount": (str, int, float),
            "offers": (dict, list),
        },
        "nested": {
            "offers": "Offer",
        },
    },
    "Article": {
        "required": ["headline", "datePublished", "author"],
        "recommended": ["dateModified", "image", "publisher", "description"],
        "types": {
            "headline": str,
            "datePublished": str,
            "author": (str, dict, list),
            "dateModified": str,
            "image": (str, list),
            "publisher": (str, dict),
            "description": str,
        },
        "nested": {},
    },
    "ItemList": {
        "required": ["itemListElement"],
        "recommended": ["name", "numberOfItems"],
        "types": {
            "itemListElement": list,
            "name": str,
            "numberOfItems": int,
        },
        "nested": {},
    },
    "ListItem": {
        "required": ["position", "item"],
        "recommended": ["name"],
        "types": {
            "position": int,
            "item": str,
            "name": str,
        },
        "nested": {},
    },
    "CollectionPage": {
        "required": ["name"],
        "recommended": ["description", "url"],
        "types": {
            "name": str,
            "url": str,
        },
        "nested": {},
    },
    "BreadcrumbList": {
        "required": ["itemListElement"],
        "recommended": ["name"],
        "types": {
            "itemListElement": list,
            "name": str,
        },
        "nested": {},
    },
    "LocalBusiness": {
        "required": ["name", "address", "telephone"],
        "recommended": ["url", "image", "priceRange", "openingHours", "geo"],
        "types": {
            "name": str,
            "address": (str, dict),
            "telephone": str,
            "url": str,
            "image": (str, list),
            "priceRange": str,
            "openingHours": (str, list),
            "geo": dict,
        },
        "nested": {},
    },
}


PAGE_EXPECTATIONS = {
    "homepage": ["Organization", "WebSite"],
    "product": ["Product", ("Offer", "AggregateOffer")],
    "collection": ["ItemList", "BreadcrumbList"],
}


MISPLACED_PROPERTY_HINTS = {
    "Product": {
        "highPrice": "AggregateOffer",
        "lowPrice": "AggregateOffer",
        "offerCount": "AggregateOffer",
    },
}


MAJOR_STATUS_SCHEMA_TYPES = {"Product", "ProductGroup"}


def audit_schema(
    extracted_schemas: List[Dict[str, Any]],
    page_type: str = None,
) -> List[Dict[str, Any]]:
    """
    Audit extracted schema objects and return flat rows for pandas reporting.

    Args:
        extracted_schemas: List of parsed schema objects
        page_type: Optional page type for completeness checks

    Returns:
        List of dictionaries describing validation status and issues
    """
    audit_rows: List[Dict[str, Any]] = []

    if page_type:
        audit_rows.extend(audit_page_completeness(page_type, extracted_schemas))

    for index, schema_item in enumerate(extracted_schemas):
        audit_rows.extend(
            _audit_schema_item(
                schema_item,
                path=f"$[{index}]",
                inherited_context=None,
                expected_type=None,
            )
        )

    if page_type and page_type.lower() == "homepage":
        audit_rows = _group_homepage_product_variant_warnings(
            audit_rows,
            extracted_schemas,
        )
    elif page_type and page_type.lower() == "product":
        audit_rows = _group_product_page_variant_warnings(
            audit_rows,
            extracted_schemas,
        )

    return audit_rows


def audit_page_completeness(
    page_type: str,
    detected_schemas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Check whether a page has all schema blocks expected for its page type.

    Args:
        page_type: Page category such as homepage, product, or collection
        detected_schemas: Parsed schema objects detected on the page

    Returns:
        List of Critical Error rows for missing required schema blocks
    """
    expected_schema_types = PAGE_EXPECTATIONS.get(page_type.lower(), [])
    detected_schema_types = _collect_schema_types(detected_schemas)
    missing_schema_types = [
        schema_expectation
        for schema_expectation in expected_schema_types
        if not _schema_expectation_met(schema_expectation, detected_schema_types)
    ]

    return [
        _audit_row(
            path="$",
            schema_type=_format_schema_expectation(schema_expectation),
            severity="Critical Error",
            issue_type="Missing Required Schema",
            field="@type",
            expected=_format_schema_expectation(schema_expectation),
            actual="missing",
            message=(
                f"{page_type} pages require a "
                f"{_format_schema_expectation(schema_expectation)} schema block."
            ),
        )
        for schema_expectation in missing_schema_types
    ]


def deep_audit(schema_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Recursively audit a JSON-LD schema object against structural standards.

    Args:
        schema_item: Parsed JSON-LD object

    Returns:
        List of dictionaries describing validation status and issues
    """
    return _audit_schema_item(
        schema_item,
        path="$",
        inherited_context=None,
        expected_type=None,
    )


def _audit_schema_item(
    schema_item: Any,
    path: str,
    inherited_context: Any,
    expected_type: Any,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if isinstance(schema_item, list):
        for index, item in enumerate(schema_item):
            rows.extend(
                _audit_schema_item(
                    item,
                    path=f"{path}[{index}]",
                    inherited_context=inherited_context,
                    expected_type=expected_type,
                )
            )
        return rows

    if not isinstance(schema_item, dict):
        return [
            _audit_row(
                path=path,
                schema_type=_display_schema_type(expected_type),
                severity="Critical Error",
                issue_type="Invalid Schema Object",
                field="@type",
                expected="dict",
                actual=type(schema_item).__name__,
                message="Schema item must be a JSON object.",
            )
        ]

    context = schema_item.get("@context", inherited_context)
    schema_type = _resolve_schema_type(schema_item, expected_type)
    graph_rows: List[Dict[str, Any]] = []

    if "@graph" in schema_item:
        graph = schema_item.get("@graph")
        if isinstance(graph, list):
            for index, graph_item in enumerate(graph):
                graph_rows.extend(
                    _audit_schema_item(
                        graph_item,
                        path=f"{path}.@graph[{index}]",
                        inherited_context=context,
                        expected_type=None,
                    )
                )
        else:
            graph_rows.append(
                _audit_row(
                    path=path,
                    schema_type=_display_schema_type(schema_type),
                    severity="Critical Error",
                    issue_type="Invalid @graph",
                    field="@graph",
                    expected="list",
                    actual=type(graph).__name__,
                    message="@graph must be an array of schema objects.",
                )
            )

    if schema_type == "Unknown" and "@type" not in schema_item:
        if graph_rows:
            return graph_rows
        return [
            _audit_row(
                path=path,
                schema_type="Unknown",
                severity="Critical Error",
                issue_type="Missing Type",
                field="@type",
                expected="Schema.org type",
                actual="missing",
                message="Schema object is missing @type.",
            )
        ]

    self_rows: List[Dict[str, Any]] = []
    if not _is_schema_org_context(context):
        self_rows.append(
            _audit_row(
                path=path,
                schema_type=_display_schema_type(schema_type),
                severity="Critical Error",
                issue_type="Invalid Context",
                field="@context",
                expected="schema.org",
                actual=_format_actual_value(context),
                message="@context must point to schema.org.",
            )
        )

    standard = SCHEMA_STANDARDS.get(schema_type)
    if not standard:
        self_rows.append(
            _audit_row(
                path=path,
                schema_type=_display_schema_type(schema_type),
                severity="Warning",
                issue_type="Unsupported Schema Type",
                field="@type",
                expected=", ".join(SCHEMA_STANDARDS.keys()),
                actual=_display_schema_type(schema_type),
                message="No structural standard is configured for this schema type.",
            )
        )
        return graph_rows + self_rows

    self_rows.extend(_audit_properties(schema_item, path, schema_type, standard))
    nested_rows = _audit_nested_schemas(schema_item, path, context, standard)
    rows = graph_rows + self_rows

    if _should_emit_parent_valid_row(schema_type, self_rows, nested_rows):
        rows.append(_valid_schema_row(path, schema_type))

    rows.extend(nested_rows)

    if not rows:
        rows.append(_valid_schema_row(path, schema_type))

    return rows


def _audit_properties(
    schema_item: Dict[str, Any],
    path: str,
    schema_type: str,
    standard: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    field_types = standard.get("types", {})

    for field in standard.get("required", []):
        if not _has_present_value(schema_item, field):
            rows.append(
                _audit_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Critical Error",
                    issue_type="Missing Required Property",
                    field=field,
                    expected=_format_expected_type(field_types.get(field)),
                    actual="missing",
                    message=f"Required property '{field}' is missing or empty.",
                )
            )
        elif field in field_types and not _matches_expected_type(schema_item[field], field_types[field]):
            rows.append(
                _type_mismatch_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Critical Error",
                    field=field,
                    value=schema_item[field],
                    expected_type=field_types[field],
                )
            )

    for field_group in standard.get("required_any", []):
        present_fields = [
            field for field in field_group if _has_present_value(schema_item, field)
        ]

        if not present_fields:
            rows.append(
                _audit_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Critical Error",
                    issue_type="Missing Required Property",
                    field=" or ".join(field_group),
                    expected="At least one present value",
                    actual="missing",
                    message=f"At least one of {', '.join(field_group)} is required.",
                )
            )
            continue

        for field in present_fields:
            if field in field_types and not _matches_expected_type(schema_item[field], field_types[field]):
                rows.append(
                    _type_mismatch_row(
                        path=path,
                        schema_type=schema_type,
                        severity="Critical Error",
                        field=field,
                        value=schema_item[field],
                        expected_type=field_types[field],
                    )
                )

    for field in standard.get("recommended", []):
        if not _has_present_value(schema_item, field):
            rows.append(
                _audit_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Warning",
                    issue_type="Missing Recommended Property",
                    field=field,
                    expected=_format_expected_type(field_types.get(field)),
                    actual="missing",
                    message=f"Recommended property '{field}' is missing or empty.",
                )
            )
        elif field in field_types and not _matches_expected_type(schema_item[field], field_types[field]):
            rows.append(
                _type_mismatch_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Warning",
                    field=field,
                    value=schema_item[field],
                    expected_type=field_types[field],
                )
            )

    rows.extend(
        _audit_unrecognized_properties(
            schema_item=schema_item,
            path=path,
            schema_type=schema_type,
            standard=standard,
        )
    )

    return rows


def _audit_unrecognized_properties(
    schema_item: Dict[str, Any],
    path: str,
    schema_type: str,
    standard: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    known_fields = _known_schema_fields(standard)
    misplaced_hints = MISPLACED_PROPERTY_HINTS.get(schema_type, {})

    for field, value in schema_item.items():
        if field.startswith("@") or field in known_fields:
            continue

        expected_owner = misplaced_hints.get(field)
        if expected_owner:
            rows.append(
                _audit_row(
                    path=path,
                    schema_type=schema_type,
                    severity="Critical Error",
                    issue_type="Invalid Property Placement",
                    field=field,
                    expected=f"{expected_owner} property",
                    actual=f"{schema_type} property",
                    message=(
                        f"Property '{field}' is not valid on {schema_type}; "
                        f"move it under {expected_owner}."
                    ),
                )
            )
            continue

        rows.append(
            _audit_row(
                path=path,
                schema_type=schema_type,
                severity="Warning",
                issue_type="Unrecognized Property",
                field=field,
                expected=f"Configured {schema_type} property",
                actual=type(value).__name__,
                message=(
                    f"Property '{field}' is not configured for {schema_type}; "
                    "verify it belongs on this schema type or add it to SCHEMA_STANDARDS."
                ),
            )
        )

    return rows


def _known_schema_fields(standard: Dict[str, Any]) -> set:
    known_fields = set(standard.get("types", {}))
    known_fields.update(standard.get("nested", {}))
    known_fields.update(standard.get("required", []))
    known_fields.update(standard.get("recommended", []))

    for field_group in standard.get("required_any", []):
        known_fields.update(field_group)

    return known_fields


def _audit_nested_schemas(
    schema_item: Dict[str, Any],
    path: str,
    context: Any,
    standard: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    nested_standards = standard.get("nested", {})

    for field, value in schema_item.items():
        if field.startswith("@"):
            continue

        expected_nested_type = nested_standards.get(field)
        if expected_nested_type:
            rows.extend(
                _audit_schema_item(
                    value,
                    path=f"{path}.{field}",
                    inherited_context=context,
                    expected_type=expected_nested_type,
                )
            )
            continue

        if isinstance(value, dict) and "@type" in value:
            rows.extend(
                _audit_schema_item(
                    value,
                    path=f"{path}.{field}",
                    inherited_context=context,
                    expected_type=None,
                )
            )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict) and "@type" in item:
                    rows.extend(
                        _audit_schema_item(
                            item,
                            path=f"{path}.{field}[{index}]",
                            inherited_context=context,
                            expected_type=None,
                        )
                    )

    return rows


def _audit_row(
    path: str,
    schema_type: str,
    severity: str,
    issue_type: str,
    field: str,
    expected: str,
    actual: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "schema_path": path,
        "schema_type": schema_type,
        "severity": severity,
        "issue_type": issue_type,
        "property": field,
        "expected": expected,
        "actual": actual,
        "message": message,
    }


def _valid_schema_row(path: str, schema_type: str) -> Dict[str, Any]:
    return _audit_row(
        path=path,
        schema_type=schema_type,
        severity="Valid",
        issue_type="Valid",
        field="",
        expected="",
        actual="",
        message="Schema passed configured structural checks.",
    )


def _should_emit_parent_valid_row(
    schema_type: str,
    self_rows: List[Dict[str, Any]],
    nested_rows: List[Dict[str, Any]],
) -> bool:
    return (
        schema_type in MAJOR_STATUS_SCHEMA_TYPES
        and not self_rows
        and bool(nested_rows)
    )


def _schema_expectation_met(schema_expectation: Any, detected_schema_types: set) -> bool:
    if isinstance(schema_expectation, str):
        return schema_expectation in detected_schema_types

    if isinstance(schema_expectation, (list, tuple, set)):
        return any(
            schema_type in detected_schema_types
            for schema_type in schema_expectation
        )

    return False


def _format_schema_expectation(schema_expectation: Any) -> str:
    if isinstance(schema_expectation, str):
        return schema_expectation

    if isinstance(schema_expectation, (list, tuple, set)):
        return " or ".join(str(schema_type) for schema_type in schema_expectation)

    return str(schema_expectation)


def _type_mismatch_row(
    path: str,
    schema_type: str,
    severity: str,
    field: str,
    value: Any,
    expected_type: Any,
) -> Dict[str, Any]:
    return _audit_row(
        path=path,
        schema_type=schema_type,
        severity=severity,
        issue_type="Invalid Property Type",
        field=field,
        expected=_format_expected_type(expected_type),
        actual=type(value).__name__,
        message=f"Property '{field}' has an unexpected data type.",
    )


def _group_homepage_product_variant_warnings(
    rows: List[Dict[str, Any]],
    detected_schemas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    variant_schema_types = {"ProductGroup", "Product", "Offer", "AggregateOffer"}
    variant_warning_rows = [
        row
        for row in rows
        if row["severity"] == "Warning"
        and row["schema_type"] in variant_schema_types
    ]

    if not variant_warning_rows:
        return rows

    product_count = _count_schema_type(detected_schemas, "Product")
    product_group_count = _count_schema_type(detected_schemas, "ProductGroup")
    offer_count = _count_schema_type(detected_schemas, "Offer")
    grouped_properties = sorted(
        {
            row["property"]
            for row in variant_warning_rows
            if row.get("property")
        }
    )

    compacted_rows = [
        row
        for row in rows
        if row not in variant_warning_rows
    ]
    compacted_rows.append(
        _audit_row(
            path="$",
            schema_type="ProductVariantSummary",
            severity="Warning",
            issue_type="Grouped Homepage Product Variant Warnings",
            field=", ".join(grouped_properties),
            expected="Recommended product variant properties",
            actual=f"{len(variant_warning_rows)} grouped warnings",
            message=(
                "Homepage contains "
                f"{product_count} product variants, "
                f"{offer_count} offers, and "
                f"{product_group_count} product groups missing recommended properties."
            ),
        )
    )

    return compacted_rows


def _group_product_page_variant_warnings(
    rows: List[Dict[str, Any]],
    detected_schemas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    repeated_warning_groups: Dict[Tuple[str, str, str, str, str, str], List[Dict[str, Any]]] = {}

    for row in rows:
        if not _is_product_variant_warning(row):
            continue

        key = (
            row["schema_type"],
            row["issue_type"],
            row["property"],
            row["expected"],
            row["actual"],
            row["message"],
        )
        repeated_warning_groups.setdefault(key, []).append(row)

    grouped_rows = [
        group_rows
        for group_rows in repeated_warning_groups.values()
        if len(group_rows) > 1
    ]
    if not grouped_rows:
        return rows

    rows_to_group = {
        id(row)
        for group_rows in grouped_rows
        for row in group_rows
    }
    compacted_rows = [
        row
        for row in rows
        if id(row) not in rows_to_group
    ]
    variant_count = _count_product_variants(detected_schemas)

    for group_rows in grouped_rows:
        first_row = group_rows[0]
        affected_count = len(group_rows)
        if variant_count and affected_count == variant_count:
            message = (
                f"Missing on all {variant_count} product variant variations."
            )
        elif variant_count:
            message = (
                f"Missing on {affected_count} of {variant_count} "
                "product variant variations."
            )
        else:
            message = (
                f"Missing on {affected_count} product variant variations."
            )

        compacted_rows.append(
            _audit_row(
                path=_collapse_variant_path(first_row["schema_path"]),
                schema_type=first_row["schema_type"],
                severity="Warning",
                issue_type="Grouped Product Variant Warning",
                field=first_row["property"],
                expected=first_row["expected"],
                actual=f"{affected_count} grouped warnings",
                message=message,
            )
        )

    return compacted_rows


def _is_product_variant_warning(row: Dict[str, Any]) -> bool:
    return (
        row["severity"] == "Warning"
        and ".hasVariant[" in row["schema_path"]
        and row["schema_type"] in {"Product", "Offer", "AggregateOffer", "Brand"}
    )


def _collapse_variant_path(path: str) -> str:
    return re.sub(r"\.hasVariant\[\d+\]", ".hasVariant[*]", path)


def _count_product_variants(schema_item: Any) -> int:
    count = 0

    if isinstance(schema_item, list):
        for item in schema_item:
            count += _count_product_variants(item)
        return count

    if not isinstance(schema_item, dict):
        return count

    item_type = schema_item.get("@type")
    normalized_type = _normalize_schema_type(item_type) if isinstance(item_type, str) else ""
    variants = schema_item.get("hasVariant")

    if normalized_type == "ProductGroup" and isinstance(variants, list):
        return sum(1 for variant in variants if isinstance(variant, dict))

    graph = schema_item.get("@graph")
    if graph is not None:
        count += _count_product_variants(graph)

    for field, value in schema_item.items():
        if field.startswith("@") or field == "hasVariant":
            continue
        if isinstance(value, (dict, list)):
            count += _count_product_variants(value)

    return count


def _count_schema_type(schema_item: Any, expected_schema_type: str) -> int:
    count = 0

    if isinstance(schema_item, list):
        for item in schema_item:
            count += _count_schema_type(item, expected_schema_type)
        return count

    if not isinstance(schema_item, dict):
        return count

    item_type = schema_item.get("@type")
    if isinstance(item_type, list):
        normalized_types = [
            _normalize_schema_type(schema_type)
            for schema_type in item_type
            if isinstance(schema_type, str)
        ]
        if expected_schema_type in normalized_types:
            count += 1
    elif isinstance(item_type, str) and _normalize_schema_type(item_type) == expected_schema_type:
        count += 1

    graph = schema_item.get("@graph")
    if graph is not None:
        count += _count_schema_type(graph, expected_schema_type)

    for field, value in schema_item.items():
        if field.startswith("@"):
            continue
        if isinstance(value, (dict, list)):
            count += _count_schema_type(value, expected_schema_type)

    return count


def _collect_schema_types(schema_item: Any) -> set:
    schema_types = set()

    if isinstance(schema_item, list):
        for item in schema_item:
            schema_types.update(_collect_schema_types(item))
        return schema_types

    if not isinstance(schema_item, dict):
        return schema_types

    item_type = schema_item.get("@type")
    if isinstance(item_type, list):
        for schema_type in item_type:
            if isinstance(schema_type, str):
                schema_types.add(_normalize_schema_type(schema_type))
    elif isinstance(item_type, str):
        schema_types.add(_normalize_schema_type(item_type))

    graph = schema_item.get("@graph")
    if graph is not None:
        schema_types.update(_collect_schema_types(graph))

    for field, value in schema_item.items():
        if field.startswith("@"):
            continue
        if isinstance(value, (dict, list)):
            schema_types.update(_collect_schema_types(value))

    return schema_types


def _resolve_schema_type(schema_item: Dict[str, Any], expected_type: Any) -> str:
    schema_type = schema_item.get("@type", expected_type)
    if isinstance(schema_type, list):
        normalized_types = [_normalize_schema_type(item) for item in schema_type if isinstance(item, str)]
        for normalized_type in normalized_types:
            if normalized_type in SCHEMA_STANDARDS:
                return normalized_type
        return normalized_types[0] if normalized_types else _display_schema_type(expected_type)
    if isinstance(schema_type, str):
        return _normalize_schema_type(schema_type)
    return _display_schema_type(expected_type)


def _normalize_schema_type(schema_type: str) -> str:
    normalized = schema_type.strip().rstrip("/")
    for separator in ("#", "/"):
        if separator in normalized:
            normalized = normalized.rsplit(separator, 1)[-1]
    if ":" in normalized and not normalized.startswith(("http://", "https://")):
        normalized = normalized.rsplit(":", 1)[-1]
    return normalized


def _display_schema_type(schema_type: Any) -> str:
    if isinstance(schema_type, str) and schema_type:
        return _normalize_schema_type(schema_type)
    return "Unknown"


def _is_schema_org_context(context: Any) -> bool:
    if isinstance(context, str):
        return "schema.org" in context.lower()
    if isinstance(context, list):
        return any(_is_schema_org_context(item) for item in context)
    if isinstance(context, dict):
        return any(_is_schema_org_context(value) for value in context.values())
    return False


def _has_present_value(schema_item: Dict[str, Any], field: str) -> bool:
    return field in schema_item and _is_present(schema_item[field])


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _matches_expected_type(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, tuple):
        return any(_matches_expected_type(value, item) for item in expected_type)

    if expected_type is float:
        return _is_float_like(value)
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type is str:
        return isinstance(value, str) and bool(value.strip())

    return isinstance(value, expected_type)


def _is_float_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _format_expected_type(expected_type: Any) -> str:
    if expected_type is None:
        return "present value"
    if isinstance(expected_type, tuple):
        return " or ".join(_format_expected_type(item) for item in expected_type)
    return getattr(expected_type, "__name__", str(expected_type))


def _format_actual_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        return value
    return type(value).__name__


class Validator:
    """Validates JSON-LD schema markup against required criteria."""

    REQUIRED_FIELDS = {
        "Organization": ["name", "url"],
        "Product": ["name", "description", "offers"],
        "Article": ["headline", "datePublished", "author"],
        "BreadcrumbList": ["itemListElement"],
    }

    @staticmethod
    def validate(schema: Dict[str, Any], schema_type: str) -> Tuple[bool, List[str]]:
        """
        Validate a schema against required fields.

        Args:
            schema: The schema object to validate
            schema_type: The expected schema type (e.g., "Organization")

        Returns:
            Tuple of (is_valid, list_of_missing_fields)
        """
        required_fields = Validator.REQUIRED_FIELDS.get(schema_type, [])
        missing_fields = []

        for field in required_fields:
            if not Validator._has_present_value(schema, field):
                missing_fields.append(field)

        is_valid = len(missing_fields) == 0
        return is_valid, missing_fields

    @staticmethod
    def validate_multiple(schemas: List[Dict[str, Any]], schema_type: str) -> Dict[str, Any]:
        """
        Validate multiple schemas of the same type.

        Args:
            schemas: List of schema objects
            schema_type: The expected schema type

        Returns:
            Validation summary report
        """
        valid_count = 0
        invalid_count = 0
        issues = []

        for idx, schema in enumerate(schemas):
            is_valid, missing_fields = Validator.validate(schema, schema_type)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
                issues.append(
                    {
                        "schema_index": idx,
                        "missing_fields": missing_fields,
                    }
                )

        return {
            "schema_type": schema_type,
            "status": "valid" if invalid_count == 0 else "invalid",
            "total": len(schemas),
            "valid": valid_count,
            "invalid": invalid_count,
            "issues": issues,
        }

    @staticmethod
    def _has_present_value(schema: Dict[str, Any], field_path: str) -> bool:
        """Check that a top-level or dotted field path exists with useful data."""
        values = Validator._get_field_values(schema, field_path.split("."))
        return any(Validator._is_present(value) for value in values)

    @staticmethod
    def _get_field_values(data: Any, path_parts: List[str]) -> List[Any]:
        if not path_parts:
            return [data]

        current_part = path_parts[0]
        remaining_parts = path_parts[1:]

        if isinstance(data, list):
            values: List[Any] = []
            for item in data:
                values.extend(Validator._get_field_values(item, path_parts))
            return values

        if isinstance(data, dict) and current_part in data:
            return Validator._get_field_values(data[current_part], remaining_parts)

        return []

    @staticmethod
    def _is_present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True
