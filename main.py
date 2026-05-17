"""
Main orchestration for the schema auditor application.
"""

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from config.settings import REQUEST_TIMEOUT, TARGET_URLS
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
    response = requests.get(
        audit_url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    extracted_schemas = extract_schema_markup(response.text)
    page_type = _infer_page_type(audit_url)
    validation_rows = audit_schema(extracted_schemas, page_type=page_type)

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
    report_data.to_csv(output_path, index=False)
    log_message(f"Report generated: {output_path}")

    return report_data


def _build_report_path(url: str) -> Path:
    parsed_url = urlparse(url)
    filename_base = sanitize_filename(parsed_url.netloc or url) or "audit_report"
    return REPORTS_DIR / f"{filename_base}_schema_audit.csv"


def _infer_page_type(url: str) -> str:
    parsed_url = urlparse(url)
    path = parsed_url.path.strip("/")

    if not path:
        return "homepage"
    if path.startswith("products/"):
        return "product"
    if path.startswith("collections/"):
        return "collection"

    return ""


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
