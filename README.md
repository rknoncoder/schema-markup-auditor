# Schema Markup Auditor

A Python application for auditing JSON-LD schema markup across websites.

## Overview

The auditor fetches configured URLs, extracts JSON-LD schema objects, validates required schema types and fields, and writes a CSV report.

It supports common JSON-LD publishing patterns, including:

- Single schema objects
- Arrays of schema objects
- `@graph` containers
- Full schema.org type URLs such as `https://schema.org/Organization`
- Prefixed schema types such as `schema:Organization`

## Project Structure

```text
schema-markup-auditor/
├── config/
│   └── settings.py          # Target URLs, required schema types, and crawl settings
├── core/
│   ├── crawler.py           # Fetches HTML pages with requests or Playwright
│   ├── extractor.py         # Parses HTML and extracts JSON-LD schema objects
│   └── validator.py         # Validates extracted schemas
├── reports/                 # Generated CSV audit reports
├── tests/
│   └── test_auditor.py      # Unit tests for extraction, validation, and reports
├── utils/
│   └── helpers.py           # URL cleaning, validation, and logging helpers
├── main.py                  # Entry point
└── requirements.txt
```

## Installation

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

For JavaScript-rendered pages, install Playwright browser binaries:

```bash
playwright install chromium
```

## Configuration

Edit `config/settings.py`:

```python
TARGET_URLS = [
    "https://example.com",
]

REQUIRED_SCHEMA_TYPES = [
    "Organization",
    "Product",
    "Article",
    "BreadcrumbList",
]

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USE_HEADLESS_BROWSER = False
```

Set `USE_HEADLESS_BROWSER = True` when schema is injected by client-side JavaScript and regular HTML fetching does not see it.

## Usage

```bash
python main.py
```

The CSV report is written to:

```text
reports/audit_report.csv
```

## Testing

```bash
python -m unittest discover
```

## Notes

This project performs lightweight schema presence checks. It does not replace Google's Rich Results Test or full Schema.org validation, but it is useful for quickly finding missing schema types and required fields across a list of URLs.
