"""
Schema extraction module.

Parses HTML and extracts <script type="application/ld+json"> tags.
"""

import json
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _flatten_schema_data(schema_data: Any) -> List[Dict[str, Any]]:
    """
    Normalize JSON-LD into individual schema objects.

    JSON-LD is commonly published as a single object, an array of objects,
    or an object containing an @graph list.
    """
    if isinstance(schema_data, list):
        flattened: List[Dict[str, Any]] = []
        for item in schema_data:
            flattened.extend(_flatten_schema_data(item))
        return flattened

    if not isinstance(schema_data, dict):
        return []

    schemas = []
    if "@type" in schema_data:
        schemas.append(schema_data)

    graph = schema_data.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            schemas.extend(_flatten_schema_data(item))
    elif "@type" not in schema_data:
        schemas.append(schema_data)

    return schemas


def extract_json_ld(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract and parse JSON-LD schema objects from HTML content.

    Args:
        html_content: Raw HTML content as string

    Returns:
        Flat list of parsed JSON-LD schema objects
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
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON-LD: {e}")
            continue

        schemas.extend(_flatten_schema_data(schema_data))

    return schemas


def extract_microdata(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract simple schema.org Microdata objects from HTML content.

    Args:
        html_content: Raw HTML content as string

    Returns:
        Flat list of parsed Microdata schema objects
    """
    soup = BeautifulSoup(html_content, "html.parser")
    schemas: List[Dict[str, Any]] = []
    base_url = _get_base_url(soup)

    for item in soup.select("[itemscope][itemtype]"):
        if _has_itemscope_ancestor(item):
            continue

        item_type = item.get("itemtype", "")
        if "schema.org" not in item_type:
            continue

        schema = _parse_microdata_item(item, base_url)
        if schema:
            schemas.append(schema)

    return schemas


def extract_schema_markup(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract supported schema markup formats from HTML content.

    Currently supports JSON-LD and simple schema.org Microdata.
    """
    return extract_json_ld(html_content) + extract_microdata(html_content)


def _parse_microdata_item(item: Any, base_url: str = "") -> Dict[str, Any]:
    schema: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": _normalize_schema_type(item.get("itemtype", "")),
    }

    for prop in item.select("[itemprop]"):
        if prop is item:
            continue

        nested_parent = prop.find_parent(attrs={"itemscope": True, "itemtype": True})
        if nested_parent is not None and nested_parent is not item and not prop.has_attr("itemscope"):
            continue

        prop_name = prop.get("itemprop")
        if not prop_name:
            continue

        if prop.has_attr("itemscope"):
            prop_value = _parse_microdata_item(prop, base_url)
        else:
            prop_value = _extract_microdata_value(prop, base_url)

        if not _is_present(prop_value):
            continue

        _add_microdata_property(schema, prop_name, prop_value)

    if schema.get("@type") == "Organization" and "name" not in schema:
        fallback_name = item.get_text(" ", strip=True)
        if fallback_name:
            schema["name"] = fallback_name

    return schema


def _extract_microdata_value(prop: Any, base_url: str = "") -> Any:
    if prop.name in {"meta", "data"}:
        return prop.get("content") or prop.get("value")
    if prop.name in {"audio", "embed", "iframe", "img", "source", "track", "video"}:
        return _make_absolute_url(prop.get("src"), base_url)
    if prop.name in {"a", "area", "link"}:
        return _make_absolute_url(prop.get("href"), base_url)
    if prop.name == "object":
        return _make_absolute_url(prop.get("data"), base_url)
    if prop.name == "time":
        return prop.get("datetime") or prop.get_text(strip=True)
    return prop.get("content") or prop.get_text(" ", strip=True)


def _add_microdata_property(schema: Dict[str, Any], prop_name: str, prop_value: Any) -> None:
    if prop_name in schema:
        existing_value = schema[prop_name]
        if isinstance(existing_value, list):
            existing_value.append(prop_value)
        else:
            schema[prop_name] = [existing_value, prop_value]
    else:
        schema[prop_name] = prop_value


def _has_itemscope_ancestor(item: Any) -> bool:
    return item.find_parent(attrs={"itemscope": True, "itemtype": True}) is not None


def _get_base_url(soup: BeautifulSoup) -> str:
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    if canonical and canonical.get("href"):
        return canonical["href"]

    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        return og_url["content"]

    return ""


def _make_absolute_url(value: Any, base_url: str) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    if not base_url:
        return value
    return urljoin(base_url, value)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


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
        return extract_json_ld(html_content)

    @staticmethod
    def _flatten_schema_data(schema_data: Any) -> List[Dict[str, Any]]:
        """
        Normalize JSON-LD into individual schema objects.

        JSON-LD is commonly published as a single object, an array of objects,
        or an object containing an @graph list.
        """
        return _flatten_schema_data(schema_data)

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
        return _normalize_schema_type(schema_type)


def _normalize_schema_type(schema_type: str) -> str:
    """Normalize full schema.org URLs and prefixed values to short names."""
    normalized = schema_type.strip().rstrip("/")
    for separator in ("#", "/"):
        if separator in normalized:
            normalized = normalized.rsplit(separator, 1)[-1]
    if ":" in normalized and not normalized.startswith(("http://", "https://")):
        normalized = normalized.rsplit(":", 1)[-1]
    return normalized
