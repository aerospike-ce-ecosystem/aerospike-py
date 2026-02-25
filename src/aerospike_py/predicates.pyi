"""Type stubs for aerospike_py.predicates module.

Predicate helpers for building secondary index query filters.
Pass the returned tuple to ``query.where()``::

    from aerospike_py import predicates as p

    query = client.query("test", "demo")
    query.where(p.equals("age", 30))
"""

from typing import Any

def equals(bin_name: str, val: Any) -> tuple[str, str, Any]:
    """Filter records where *bin_name* equals *val* (integer or string).

    Requires a secondary index on the bin.

    Example::

        query.where(predicates.equals("status", "active"))
    """

def between(bin_name: str, min_val: Any, max_val: Any) -> tuple[str, str, Any, Any]:
    """Filter records where *bin_name* is in the range [min_val, max_val] (inclusive).

    Requires a numeric secondary index on the bin.

    Example::

        query.where(predicates.between("age", 18, 65))
    """

def contains(bin_name: str, index_type: int, val: Any) -> tuple[str, str, int, Any]:
    """Filter records where a collection bin contains *val*.

    Args:
        bin_name: Name of the bin holding a list or map.
        index_type: One of ``INDEX_TYPE_LIST``, ``INDEX_TYPE_MAPKEYS``,
            or ``INDEX_TYPE_MAPVALUES``.
        val: The value to search for within the collection.

    Example::

        query.where(predicates.contains("tags", INDEX_TYPE_LIST, "python"))
    """

def geo_within_geojson_region(bin_name: str, geojson: str) -> tuple[str, str, str]:
    """Filter records whose geo bin falls within the given GeoJSON region.

    Warning:
        Geo filters are not yet supported. Using this predicate will raise
        ``ClientError`` at query execution time.
    """

def geo_within_radius(bin_name: str, lat: float, lng: float, radius: float) -> tuple[str, str, float, float, float]:
    """Filter records whose geo bin falls within *radius* meters of (*lat*, *lng*).

    Warning:
        Geo filters are not yet supported. Using this predicate will raise
        ``ClientError`` at query execution time.
    """

def geo_contains_geojson_point(bin_name: str, geojson: str) -> tuple[str, str, str]:
    """Filter records whose geo region bin contains the given GeoJSON point.

    Warning:
        Geo filters are not yet supported. Using this predicate will raise
        ``ClientError`` at query execution time.
    """
