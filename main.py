"""
Main entry point for the schema auditor application.
"""

import csv
import json
from pathlib import Path

from config.settings import (
    MAX_RETRIES,
    REQUIRED_SCHEMA_TYPES,
    REQUEST_TIMEOUT,
    TARGET_URLS,
    USE_HEADLESS_BROWSER,
)
from core.crawler import Crawler
from core.extractor import Extractor
from core.validator import Validator
from utils.helpers import clean_url, is_valid_url, log_message


def audit_url(url: str, crawler: Crawler, required_types: list) -> dict:
    """
    Audit a single URL for schema markup.

    Args:
        url: The URL to audit
        crawler: Crawler instance
        required_types: List of required schema types

    Returns:
        Audit results dictionary
    """
    log_message(f"Auditing {url}")

    # Fetch HTML
    html_content = crawler.fetch(url)
    if not html_content:
        return {"url": url, "status": "failed", "error": "Failed to fetch URL"}

    # Extract schemas
    schemas = Extractor.extract(html_content)
    if not schemas:
        return {"url": url, "status": "no_schemas", "found_schemas": 0}

    # Validate required schema types
    results = {
        "url": url,
        "status": "success",
        "found_schemas": len(schemas),
        "validations": {},
    }

    for schema_type in required_types:
        filtered = Extractor.filter_by_type(schemas, schema_type)
        if filtered:
            validation = Validator.validate_multiple(filtered, schema_type)
            results["validations"][schema_type] = validation
        else:
            results["validations"][schema_type] = {"status": "not_found"}

    return results


def generate_report(audit_results: list, output_file: str = "reports/audit_report.csv"):
    """
    Generate a CSV audit report.

    Args:
        audit_results: List of audit result dictionaries
        output_file: Output file path
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "URL",
                "Audit Status",
                "Found Schemas",
                "Schema Type",
                "Type Status",
                "Total",
                "Valid",
                "Invalid",
                "Issues",
            ]
        )

        for result in audit_results:
            validations = result.get("validations", {})
            if not validations:
                writer.writerow(
                    [
                        result["url"],
                        result["status"],
                        result.get("found_schemas", 0),
                        "",
                        result.get("error", ""),
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                continue

            for schema_type, validation in validations.items():
                writer.writerow(
                    [
                        result["url"],
                        result["status"],
                        result.get("found_schemas", 0),
                        schema_type,
                        validation.get("status", "checked"),
                        validation.get("total", 0),
                        validation.get("valid", 0),
                        validation.get("invalid", 0),
                        json.dumps(validation.get("issues", []), ensure_ascii=False),
                    ]
                )

    log_message(f"Report generated: {output_path}")


def main():
    """Main execution function."""
    if not TARGET_URLS:
        log_message("No target URLs configured. Edit config/settings.py to add URLs.", "WARNING")
        return

    log_message("Starting schema auditor")

    # Initialize crawler
    crawler = Crawler(
        timeout=REQUEST_TIMEOUT,
        use_playwright=USE_HEADLESS_BROWSER,
        max_retries=MAX_RETRIES,
    )

    # Audit each URL
    results = []
    for url in TARGET_URLS:
        try:
            clean = clean_url(url)
            if not is_valid_url(clean):
                log_message(f"Skipping invalid URL: {url}", "WARNING")
                results.append({"url": url, "status": "invalid_url", "error": "Invalid URL"})
                continue

            result = audit_url(clean, crawler, REQUIRED_SCHEMA_TYPES)
            results.append(result)
        except Exception as e:
            log_message(f"Error auditing {url}: {e}", "ERROR")
            results.append({"url": url, "status": "error", "error": str(e)})

    # Generate report
    if results:
        generate_report(results)

    log_message("Audit complete")


if __name__ == "__main__":
    main()
