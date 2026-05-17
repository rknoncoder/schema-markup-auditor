"""
Schema validation module.

Validates extracted schema fields against criteria.
"""

from typing import Any, Dict, List, Tuple


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
