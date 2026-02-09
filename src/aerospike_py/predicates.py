"""Predicate helpers for secondary index queries.

Usage:
    import aerospike_py
    from aerospike_py import predicates as p

    query = client.query("test", "demo")
    query.where(p.equals("age", 30))
    query.where(p.between("age", 18, 65))
"""

from typing import Any

__all__ = [
    "equals",
    "between",
    "contains",
    "geo_within_geojson_region",
    "geo_within_radius",
    "geo_contains_geojson_point",
]


def equals(bin_name: str, val: Any) -> tuple[str, str, Any]:
    """Create an equality predicate for a secondary index query."""
    return ("equals", bin_name, val)


def between(bin_name: str, min_val: Any, max_val: Any) -> tuple[str, str, Any, Any]:
    """Create a range predicate for a secondary index query."""
    return ("between", bin_name, min_val, max_val)


def contains(bin_name: str, index_type: int, val: Any) -> tuple[str, str, int, Any]:
    """Create a contains predicate for collection index queries.

    Args:
        bin_name: Name of the bin.
        index_type: Collection index type (INDEX_TYPE_LIST, INDEX_TYPE_MAPKEYS, INDEX_TYPE_MAPVALUES).
        val: The value to search for.
    """
    return ("contains", bin_name, index_type, val)


def geo_within_geojson_region(bin_name: str, geojson: str) -> tuple[str, str, str]:
    """Create a geospatial 'within region' predicate."""
    return ("geo_within_geojson_region", bin_name, geojson)


def geo_within_radius(
    bin_name: str, lat: float, lng: float, radius: float
) -> tuple[str, str, float, float, float]:
    """Create a geospatial 'within radius' predicate."""
    return ("geo_within_radius", bin_name, lat, lng, radius)


def geo_contains_geojson_point(bin_name: str, geojson: str) -> tuple[str, str, str]:
    """Create a geospatial 'contains point' predicate."""
    return ("geo_contains_point", bin_name, geojson)
