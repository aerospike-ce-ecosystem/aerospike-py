"""Unit tests for predicates helpers (no server required)."""

import warnings

import pytest

from aerospike_py import (
    INDEX_TYPE_LIST,
    INDEX_TYPE_MAPKEYS,
    INDEX_TYPE_MAPVALUES,
)
from aerospike_py import predicates as p

# ── Equals predicate ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "bin_name,val",
    [
        ("age", 30),
        ("name", "Alice"),
        ("count", 0),
        ("flag", True),
        ("score", 3.14),
        ("tag", ""),
        ("big", 2**63 - 1),
    ],
    ids=["int", "string", "zero", "bool", "float", "empty_string", "large_int"],
)
def test_equals(bin_name, val):
    """equals() produces correct 3-tuple for various value types."""
    result = p.equals(bin_name, val)
    assert result == ("equals", bin_name, val)
    assert len(result) == 3
    assert result[0] == "equals"


# ── Between predicate ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "bin_name,min_val,max_val",
    [
        ("age", 18, 65),
        ("score", 0.0, 100.0),
        ("count", 0, 0),
        ("level", -100, 100),
        ("timestamp", 0, 2**32),
    ],
    ids=["int_range", "float_range", "same_val", "negative_range", "large_range"],
)
def test_between(bin_name, min_val, max_val):
    """between() produces correct 4-tuple for various ranges."""
    result = p.between(bin_name, min_val, max_val)
    assert result == ("between", bin_name, min_val, max_val)
    assert len(result) == 4
    assert result[0] == "between"


# ── Contains predicate ────────────────────────────────────────────


@pytest.mark.parametrize(
    "index_type,val,type_name",
    [
        (INDEX_TYPE_LIST, "python", "list"),
        (INDEX_TYPE_MAPKEYS, "key1", "mapkeys"),
        (INDEX_TYPE_MAPVALUES, 42, "mapvalues"),
    ],
    ids=["list", "mapkeys", "mapvalues"],
)
def test_contains(index_type, val, type_name):
    """contains() produces correct 4-tuple for each index type."""
    result = p.contains("mybin", index_type, val)
    assert result == ("contains", "mybin", index_type, val)
    assert len(result) == 4
    assert result[0] == "contains"


# ── Geo predicates ────────────────────────────────────────────────


class TestGeoPredicates:
    def test_geo_within_geojson_region(self):
        geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = p.geo_within_geojson_region("location", geojson)
        assert result == ("geo_within_geojson_region", "location", geojson)
        assert len(result) == 3
        assert any("not yet supported" in str(x.message) for x in w)

    def test_geo_within_radius(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = p.geo_within_radius("location", 37.7749, -122.4194, 1000.0)
        assert result == ("geo_within_radius", "location", 37.7749, -122.4194, 1000.0)
        assert len(result) == 5
        assert any("not yet supported" in str(x.message) for x in w)

    def test_geo_contains_geojson_point(self):
        geojson = '{"type": "Point", "coordinates": [0.5, 0.5]}'
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = p.geo_contains_geojson_point("region", geojson)
        assert result == ("geo_contains_geojson_point", "region", geojson)
        assert len(result) == 3
        assert any("not yet supported" in str(x.message) for x in w)

    @pytest.mark.parametrize(
        "func,args",
        [
            (p.geo_within_geojson_region, ("loc", '{"type":"Point"}')),
            (p.geo_within_radius, ("loc", 0.0, 0.0, 100.0)),
            (p.geo_contains_geojson_point, ("loc", '{"type":"Point"}')),
        ],
        ids=["within_region", "within_radius", "contains_point"],
    )
    def test_geo_predicates_emit_future_warning(self, func, args):
        """All geo predicates emit FutureWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            func(*args)
            future_warns = [x for x in w if issubclass(x.category, FutureWarning)]
            assert len(future_warns) >= 1


# ── Module access tests ───────────────────────────────────────────


class TestPredicateModule:
    def test_module_accessible_from_aerospike_py(self):
        import aerospike_py

        assert hasattr(aerospike_py, "predicates")
        assert aerospike_py.predicates is p

    def test_all_exports(self):
        """Every symbol in __all__ is importable."""
        for name in p.__all__:
            assert hasattr(p, name), f"predicates.__all__ contains '{name}' but it is not defined"
