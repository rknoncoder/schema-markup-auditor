"""
Schema extraction module.

Parses HTML and extracts <script type="application/ld+json"> tags.
"""

import json
from typing import Any, Dict, List
from bs4 import BeautifulSoup


class Extractor:
    """Extracts JSON-LD schema markup from HTML content."""

    @staticmethod
    def extract(html_content: str) -> List[Dict[str, Any]]:
        """
        Extract all JSON-LD schema scripts from HTML.

        Args:
            html_content: Raw HTML content as string

        Returns:
            List of parsed JSON-LD objects
        """
        soup = BeautifulSoup(html_content, "html.parser")
        schemas: List[Dict[str, Any]] = []

        script_tags = soup.find_all(
            "script",
            type=lambda value: value
            and value.split(";")[0].strip().lower() == "application/ld+json",
        )

        for script_tag in script_tags:
            script_content = script_tag.string or script_tag.get_text()
            if not script_content or not script_content.strip():
                continue

            try:
                schema_data = json.loads(script_content)
                schemas.extend(Extractor._flatten_schema_data(schema_data))
            except (TypeError, json.JSONDecodeError) as e:
                print(f"Error parsing JSON-LD: {e}")

        return schemas

    @staticmethod
    def _flatten_schema_data(schema_data: Any) -> List[Dict[str, Any]]:
        """
        Normalize JSON-LD into individual schema objects.

        JSON-LD is commonly published as a single object, an array of objects,
        or an object containing an @graph list.
        """
        if isinstance(schema_data, list):
            flattened: List[Dict[str, Any]] = []
            for item in schema_data:
                flattened.extend(Extractor._flatten_schema_data(item))
            return flattened

        if not isinstance(schema_data, dict):
            return []

        schemas = []
        if "@type" in schema_data:
            schemas.append(schema_data)

        graph = schema_data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                schemas.extend(Extractor._flatten_schema_data(item))
        elif "@type" not in schema_data:
            schemas.append(schema_data)

        return schemas

    @staticmethod
    def filter_by_type(schemas: List[Dict[str, Any]], schema_type: str) -> List[Dict[str, Any]]:
        """
        Filter schemas by @type.

        Args:
            schemas: List of schema objects
            schema_type: The @type to filter by (e.g., "Organization")

        Returns:
            Filtered list of schemas
        """
        filtered = []
        for schema in schemas:
            if isinstance(schema, dict):
                if schema_type in Extractor._get_schema_types(schema):
                    filtered.append(schema)
        return filtered

    @staticmethod
    def _get_schema_types(schema: Dict[str, Any]) -> List[str]:
        """Return normalized type names from a schema object's @type value."""
        schema_types = schema.get("@type", [])
        if isinstance(schema_types, str):
            schema_types = [schema_types]
        if not isinstance(schema_types, list):
            return []

        return [
            Extractor._normalize_schema_type(schema_type)
            for schema_type in schema_types
            if isinstance(schema_type, str)
        ]

    @staticmethod
    def _normalize_schema_type(schema_type: str) -> str:
        """Normalize full schema.org URLs and prefixed values to short names."""
        normalized = schema_type.strip().rstrip("/")
        for separator in ("#", "/"):
            if separator in normalized:
                normalized = normalized.rsplit(separator, 1)[-1]
        if ":" in normalized and not normalized.startswith(("http://", "https://")):
            normalized = normalized.rsplit(":", 1)[-1]
        return normalized
