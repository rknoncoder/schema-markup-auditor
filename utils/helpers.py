"""
Helper utilities for the schema auditor.

Small helper functions for URL cleaning, logging, date formats, etc.
"""

import re
from datetime import datetime


def clean_url(url: str) -> str:
    """
    Clean and normalize a URL.

    Args:
        url: The URL to clean

    Returns:
        Cleaned URL
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_valid_url(url: str) -> bool:
    """
    Validate if a string is a valid URL.

    Args:
        url: The URL to validate

    Returns:
        True if valid, False otherwise
    """
    url_pattern = re.compile(
        r"^https?://"  # http or https
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return url_pattern.match(url) is not None


def get_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        Current timestamp string
    """
    return datetime.now().isoformat()


def log_message(message: str, level: str = "INFO") -> None:
    """
    Log a message with timestamp.

    Args:
        message: The message to log
        level: Log level (INFO, WARNING, ERROR)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string for use as a filename.

    Args:
        filename: The filename to sanitize

    Returns:
        Safe filename
    """
    # Remove invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "_", filename)
    return sanitized[:255]  # Limit length
