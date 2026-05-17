"""
Configuration settings for the schema auditor.

This module contains target URLs, required schema types, and timeout configurations.
"""

# Target URLs to audit
TARGET_URLS = [
    # Add your URLs here
    # Example: "https://example.com",
]

# Required schema types to check for
REQUIRED_SCHEMA_TYPES = [
    "Organization",
    "Product",
    "Article",
    "BreadcrumbList",
    # Add more schema types as needed
]

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Maximum number of retries for failed requests
MAX_RETRIES = 3

# Enable headless browser mode (True for Playwright, False for simple requests)
USE_HEADLESS_BROWSER = False
