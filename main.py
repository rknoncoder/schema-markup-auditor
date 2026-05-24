"""
Main orchestration for the schema auditor application.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import pandas as pd
import requests

from config.settings import MAX_RETRIES, REQUEST_TIMEOUT, TARGET_URLS, USE_HEADLESS_BROWSER
from core.crawler import Crawler
from core.extractor import extract_schema_markup
from core.validator import audit_schema
from utils.helpers import clean_url, is_valid_url, log_message, sanitize_filename


USER_AGENT = (
    "Mozilla/5.0 (compatible; SchemaMarkupAuditor/1.0; "
    "+https://github.com/rknoncoder/schema-markup-auditor)"
)
REPORTS_DIR = Path("reports")


def run_audit(url: str) -> pd.DataFrame:
    """
    Fetch a URL, extract JSON-LD, validate schemas, and write a CSV report.

    Args:
        url: URL to audit

    Returns:
        Pandas DataFrame containing validation rows
    """
    audit_url = clean_url(url)
    if not is_valid_url(audit_url):
        raise ValueError(f"Invalid URL: {url}")

    log_message(f"Auditing {audit_url}")
    html_content = _fetch_page_html(audit_url)
    extracted_schemas = extract_schema_markup(html_content)
    page_type = _infer_page_type(audit_url, extracted_schemas)
    audit_schemas = _prepare_schemas_for_page_type(extracted_schemas, page_type)
    validation_rows = audit_schema(audit_schemas, page_type=page_type)

    if not validation_rows:
        validation_rows = [
            {
                "schema_path": "",
                "schema_type": "",
                "severity": "Warning",
                "issue_type": "No Schema Found",
                "property": "",
                "expected": "Schema markup",
                "actual": "none",
                "message": "No supported schema markup was found on the page.",
            }
        ]

    report_data = pd.DataFrame(validation_rows)
    report_data.insert(0, "url", audit_url)

    output_path = _build_report_path(audit_url)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_report(output_path, report_data, extracted_schemas, validation_rows)
    log_message(f"Report generated: {output_path}")

    return report_data


def _write_report(
    output_path: Path,
    report_data: pd.DataFrame,
    extracted_schemas: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
) -> None:
    summary_lines = _build_executive_summary(extracted_schemas, validation_rows)

    with output_path.open("w", encoding="utf-8", newline="") as report_file:
        for line in summary_lines:
            report_file.write(f"{line}\n")
        report_data.to_csv(report_file, index=False)


def _build_executive_summary(
    extracted_schemas: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
) -> List[str]:
    return [
        "# --------------------------------------------------",
        "# SCHEMA AUDIT EXECUTIVE SUMMARY",
        f"# Total Schemas Detected: {_count_detected_schema_blocks(extracted_schemas)}",
        f"# Total Fully Valid Blocks: {_count_rows_by_severity(validation_rows, 'Valid')}",
        f"# Total Warnings Found: {_count_rows_by_severity(validation_rows, 'Warning')}",
        f"# Total Critical Errors Found: {_count_rows_by_severity(validation_rows, 'Critical Error')}",
        "# --------------------------------------------------",
    ]


def _count_detected_schema_blocks(schema_item: Any) -> int:
    if isinstance(schema_item, list):
        return sum(_count_detected_schema_blocks(item) for item in schema_item)

    if not isinstance(schema_item, dict):
        return 0

    count = 1 if "@type" in schema_item else 0
    for value in schema_item.values():
        if isinstance(value, (dict, list)):
            count += _count_detected_schema_blocks(value)

    return count


def _count_rows_by_severity(
    validation_rows: List[Dict[str, Any]],
    severity: str,
) -> int:
    return sum(1 for row in validation_rows if row.get("severity") == severity)


def _fetch_page_html(url: str) -> str:
    if USE_HEADLESS_BROWSER:
        log_message("Using headless browser rendering for JavaScript schemas")
        crawler = Crawler(
            timeout=REQUEST_TIMEOUT,
            use_playwright=True,
            max_retries=MAX_RETRIES,
        )
        html_content = crawler.fetch(url)
        if html_content is None:
            raise RuntimeError(f"Unable to fetch rendered HTML for {url}")
        return html_content

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _build_report_path(url: str) -> Path:
    parsed_url = urlparse(url)
    filename_parts = [parsed_url.netloc or url]
    path_part = parsed_url.path.strip("/").replace("/", "_")

    if path_part:
        filename_parts.append(path_part)
    if parsed_url.query:
        filename_parts.append(parsed_url.query)

    filename_base = sanitize_filename("_".join(filename_parts)) or "audit_report"
    return REPORTS_DIR / f"{filename_base}_schema_audit.csv"


def extract_storefront_node(data: Any) -> Optional[Dict[str, Any]]:
    """
    Recursively scan JSON-LD data for a Product or ProductGroup block.

    Shopify themes can wrap storefront schema inside WebPage.about or
    WebPage.mainEntity shells. Isolating that node keeps product-specific
    grouping and variant deduplication active.
    """
    return _extract_storefront_node(data, parent_context=None)


def _extract_storefront_node(
    data: Any,
    parent_context: Any,
) -> Optional[Dict[str, Any]]:
    if isinstance(data, dict):
        current_context = data.get("@context") or parent_context

        if _has_schema_type(data, {"Product", "ProductGroup"}):
            return _with_inherited_context(data, current_context)

        for key in ("about", "mainEntity", "hasVariant", "@graph"):
            if key in data:
                result = _extract_storefront_node(data[key], current_context)
                if result:
                    return result

    elif isinstance(data, list):
        for item in data:
            result = _extract_storefront_node(item, parent_context)
            if result:
                return result

    return None


def _prepare_schemas_for_page_type(
    extracted_schemas: List[Dict[str, Any]],
    page_type: str,
) -> List[Dict[str, Any]]:
    # Keep global schemas like Organization and WebSite in the report. Product
    # routing is inferred from nested storefront nodes, while the validator can
    # still recurse into those nodes for product-specific grouping.
    return extracted_schemas


def _infer_page_type(
    url: str,
    extracted_schemas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parsed_url = urlparse(url)
    path = parsed_url.path.strip("/")

    if not path:
        return "homepage"
    if path.startswith("products/"):
        return "product"
    if path.startswith("collections/"):
        return "collection"
    if extracted_schemas and extract_storefront_node(extracted_schemas):
        return "product"

    return ""


def _has_schema_type(schema: Dict[str, Any], expected_types: Set[str]) -> bool:
    schema_type = schema.get("@type")

    if isinstance(schema_type, list):
        return any(
            _normalize_schema_type(item) in expected_types
            for item in schema_type
            if isinstance(item, str)
        )

    if isinstance(schema_type, str):
        return _normalize_schema_type(schema_type) in expected_types

    return False


def _with_inherited_context(
    schema: Dict[str, Any],
    inherited_context: Any,
) -> Dict[str, Any]:
    if not inherited_context or schema.get("@context"):
        return schema

    schema_with_context = dict(schema)
    schema_with_context["@context"] = inherited_context
    return schema_with_context


def _normalize_schema_type(schema_type: str) -> str:
    normalized = schema_type.strip().rstrip("/")
    for separator in ("#", "/"):
        if separator in normalized:
            normalized = normalized.rsplit(separator, 1)[-1]
    if ":" in normalized and not normalized.startswith(("http://", "https://")):
        normalized = normalized.rsplit(":", 1)[-1]
    return normalized


def main() -> None:
    """Run audits for configured target URLs."""
    if not TARGET_URLS:
        log_message("No target URLs configured. Edit config/settings.py to add URLs.", "WARNING")
        return

    for url in TARGET_URLS:
        try:
            run_audit(url)
        except Exception as e:
            log_message(f"Error auditing {url}: {e}", "ERROR")

    log_message("Audit complete")


if __name__ == "__main__":
    main()
