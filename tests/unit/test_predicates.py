from aerospike_py import (
    INDEX_TYPE_LIST,
    INDEX_TYPE_MAPKEYS,
    INDEX_TYPE_MAPVALUES,
)
from aerospike_py import predicates as p


class TestEquals:
    def test_integer_value(self):
        result = p.equals("age", 30)
        assert result == ("equals", "age", 30)

    def test_string_value(self):
        result = p.equals("name", "Alice")
        assert result == ("equals", "name", "Alice")

    def test_tuple_structure(self):
        result = p.equals("bin", 42)
        assert len(result) == 3
        assert result[0] == "equals"
        assert result[1] == "bin"
        assert result[2] == 42


class TestBetween:
    def test_integer_range(self):
        result = p.between("age", 18, 65)
        assert result == ("between", "age", 18, 65)

    def test_float_range(self):
        result = p.between("score", 0.0, 100.0)
        assert result == ("between", "score", 0.0, 100.0)

    def test_tuple_structure(self):
        result = p.between("bin", 1, 10)
        assert len(result) == 4
        assert result[0] == "between"
        assert result[1] == "bin"
        assert result[2] == 1
        assert result[3] == 10


class TestContains:
    def test_list_contains(self):
        result = p.contains("tags", INDEX_TYPE_LIST, "python")
        assert result == ("contains", "tags", INDEX_TYPE_LIST, "python")

    def test_mapkeys_contains(self):
        result = p.contains("metadata", INDEX_TYPE_MAPKEYS, "key1")
        assert result == ("contains", "metadata", INDEX_TYPE_MAPKEYS, "key1")

    def test_mapvalues_contains(self):
        result = p.contains("metadata", INDEX_TYPE_MAPVALUES, 42)
        assert result == ("contains", "metadata", INDEX_TYPE_MAPVALUES, 42)

    def test_tuple_structure(self):
        result = p.contains("bin", INDEX_TYPE_LIST, "val")
        assert len(result) == 4
        assert result[0] == "contains"


class TestGeoPredicates:
    def test_geo_within_geojson_region(self):
        geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
        result = p.geo_within_geojson_region("location", geojson)
        assert result == ("geo_within_geojson_region", "location", geojson)
        assert len(result) == 3

    def test_geo_within_radius(self):
        result = p.geo_within_radius("location", 37.7749, -122.4194, 1000.0)
        assert result == ("geo_within_radius", "location", 37.7749, -122.4194, 1000.0)
        assert len(result) == 5

    def test_geo_contains_geojson_point(self):
        geojson = '{"type": "Point", "coordinates": [0.5, 0.5]}'
        result = p.geo_contains_geojson_point("region", geojson)
        assert result == ("geo_contains_point", "region", geojson)
        assert len(result) == 3


class TestPredicateModule:
    def test_module_accessible_from_aerospike_py(self):
        import aerospike_py

        assert hasattr(aerospike_py, "predicates")
        assert aerospike_py.predicates is p
