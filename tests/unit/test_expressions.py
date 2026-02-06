"""Unit tests for expression filter builder (no server required)."""

from aerospike_py import exp


class TestExpValueConstructors:
    def test_int_val(self):
        e = exp.int_val(42)
        assert e["__expr__"] == "int_val"
        assert e["val"] == 42

    def test_float_val(self):
        e = exp.float_val(3.14)
        assert e["__expr__"] == "float_val"
        assert e["val"] == 3.14

    def test_string_val(self):
        e = exp.string_val("hello")
        assert e["__expr__"] == "string_val"
        assert e["val"] == "hello"

    def test_bool_val(self):
        e = exp.bool_val(True)
        assert e["__expr__"] == "bool_val"
        assert e["val"] is True

    def test_blob_val(self):
        e = exp.blob_val(b"\x01\x02")
        assert e["__expr__"] == "blob_val"
        assert e["val"] == b"\x01\x02"

    def test_list_val(self):
        e = exp.list_val([1, 2, 3])
        assert e["__expr__"] == "list_val"
        assert e["val"] == [1, 2, 3]

    def test_map_val(self):
        e = exp.map_val({"a": 1})
        assert e["__expr__"] == "map_val"
        assert e["val"] == {"a": 1}

    def test_geo_val(self):
        geo_json = '{"type":"Point","coordinates":[0.0,0.0]}'
        e = exp.geo_val(geo_json)
        assert e["__expr__"] == "geo_val"
        assert e["val"] == geo_json

    def test_nil(self):
        e = exp.nil()
        assert e["__expr__"] == "nil"

    def test_infinity(self):
        e = exp.infinity()
        assert e["__expr__"] == "infinity"

    def test_wildcard(self):
        e = exp.wildcard()
        assert e["__expr__"] == "wildcard"


class TestExpBinAccessors:
    def test_int_bin(self):
        e = exp.int_bin("age")
        assert e["__expr__"] == "int_bin"
        assert e["name"] == "age"

    def test_float_bin(self):
        e = exp.float_bin("score")
        assert e["__expr__"] == "float_bin"
        assert e["name"] == "score"

    def test_string_bin(self):
        e = exp.string_bin("name")
        assert e["__expr__"] == "string_bin"
        assert e["name"] == "name"

    def test_bool_bin(self):
        e = exp.bool_bin("active")
        assert e["__expr__"] == "bool_bin"
        assert e["name"] == "active"

    def test_blob_bin(self):
        e = exp.blob_bin("data")
        assert e["__expr__"] == "blob_bin"
        assert e["name"] == "data"

    def test_list_bin(self):
        e = exp.list_bin("items")
        assert e["__expr__"] == "list_bin"
        assert e["name"] == "items"

    def test_map_bin(self):
        e = exp.map_bin("meta")
        assert e["__expr__"] == "map_bin"
        assert e["name"] == "meta"

    def test_geo_bin(self):
        e = exp.geo_bin("location")
        assert e["__expr__"] == "geo_bin"
        assert e["name"] == "location"

    def test_hll_bin(self):
        e = exp.hll_bin("hll_count")
        assert e["__expr__"] == "hll_bin"
        assert e["name"] == "hll_count"

    def test_bin_exists(self):
        e = exp.bin_exists("mybin")
        assert e["__expr__"] == "bin_exists"
        assert e["name"] == "mybin"

    def test_bin_type(self):
        e = exp.bin_type("mybin")
        assert e["__expr__"] == "bin_type"
        assert e["name"] == "mybin"


class TestExpRecordMetadata:
    def test_key(self):
        e = exp.key(exp.EXP_TYPE_INT)
        assert e["__expr__"] == "key"
        assert e["exp_type"] == 2

    def test_key_exists(self):
        e = exp.key_exists()
        assert e["__expr__"] == "key_exists"

    def test_set_name(self):
        e = exp.set_name()
        assert e["__expr__"] == "set_name"

    def test_record_size(self):
        e = exp.record_size()
        assert e["__expr__"] == "record_size"

    def test_ttl(self):
        e = exp.ttl()
        assert e["__expr__"] == "ttl"

    def test_last_update(self):
        e = exp.last_update()
        assert e["__expr__"] == "last_update"

    def test_since_update(self):
        e = exp.since_update()
        assert e["__expr__"] == "since_update"

    def test_void_time(self):
        e = exp.void_time()
        assert e["__expr__"] == "void_time"

    def test_is_tombstone(self):
        e = exp.is_tombstone()
        assert e["__expr__"] == "is_tombstone"

    def test_digest_modulo(self):
        e = exp.digest_modulo(3)
        assert e["__expr__"] == "digest_modulo"
        assert e["modulo"] == 3


class TestExpComparisons:
    def test_eq(self):
        e = exp.eq(exp.int_bin("age"), exp.int_val(21))
        assert e["__expr__"] == "eq"
        assert e["left"]["__expr__"] == "int_bin"
        assert e["right"]["__expr__"] == "int_val"

    def test_ne(self):
        e = exp.ne(exp.string_bin("status"), exp.string_val("deleted"))
        assert e["__expr__"] == "ne"

    def test_gt(self):
        e = exp.gt(exp.int_bin("count"), exp.int_val(0))
        assert e["__expr__"] == "gt"

    def test_ge(self):
        e = exp.ge(exp.float_bin("score"), exp.float_val(3.5))
        assert e["__expr__"] == "ge"

    def test_lt(self):
        e = exp.lt(exp.int_bin("age"), exp.int_val(100))
        assert e["__expr__"] == "lt"

    def test_le(self):
        e = exp.le(exp.int_bin("rank"), exp.int_val(10))
        assert e["__expr__"] == "le"


class TestExpLogical:
    def test_and(self):
        e = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(18)),
            exp.lt(exp.int_bin("age"), exp.int_val(65)),
        )
        assert e["__expr__"] == "and"
        assert len(e["exprs"]) == 2

    def test_or(self):
        e = exp.or_(
            exp.eq(exp.string_bin("role"), exp.string_val("admin")),
            exp.eq(exp.string_bin("role"), exp.string_val("superuser")),
        )
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 2

    def test_not(self):
        e = exp.not_(exp.eq(exp.int_bin("deleted"), exp.int_val(1)))
        assert e["__expr__"] == "not"
        assert e["expr"]["__expr__"] == "eq"

    def test_xor(self):
        e = exp.xor_(exp.bool_val(True), exp.bool_val(False))
        assert e["__expr__"] == "xor"
        assert len(e["exprs"]) == 2


class TestExpNumeric:
    def test_num_add(self):
        e = exp.num_add(exp.int_bin("a"), exp.int_val(1))
        assert e["__expr__"] == "num_add"
        assert len(e["exprs"]) == 2

    def test_num_mod(self):
        e = exp.num_mod(exp.int_bin("counter"), exp.int_val(10))
        assert e["__expr__"] == "num_mod"
        assert len(e["exprs"]) == 2

    def test_to_int(self):
        e = exp.to_int(exp.float_bin("score"))
        assert e["__expr__"] == "to_int"
        assert len(e["exprs"]) == 1


class TestExpIntBitwise:
    def test_int_and(self):
        e = exp.int_and(exp.int_bin("flags"), exp.int_val(0xFF))
        assert e["__expr__"] == "int_and"
        assert len(e["exprs"]) == 2


class TestExpPatternMatching:
    def test_regex_compare(self):
        e = exp.regex_compare("prefix.*", 0, exp.string_bin("name"))
        assert e["__expr__"] == "regex_compare"
        assert e["regex"] == "prefix.*"
        assert e["flags"] == 0
        assert e["bin"]["__expr__"] == "string_bin"

    def test_geo_compare(self):
        e = exp.geo_compare(exp.geo_bin("loc"), exp.geo_val('{"type":"Point"}'))
        assert e["__expr__"] == "geo_compare"


class TestExpControlFlow:
    def test_cond(self):
        e = exp.cond(
            exp.eq(exp.int_bin("type"), exp.int_val(1)),
            exp.string_val("type_a"),
            exp.string_val("other"),
        )
        assert e["__expr__"] == "cond"
        assert len(e["exprs"]) == 3

    def test_let_and_var(self):
        e = exp.let_(
            exp.def_("x", exp.int_bin("count")),
            exp.gt(exp.var("x"), exp.int_val(0)),
        )
        assert e["__expr__"] == "let"
        assert len(e["exprs"]) == 2
        assert e["exprs"][0]["__expr__"] == "def"
        assert e["exprs"][0]["name"] == "x"


class TestExpTypeConstants:
    def test_type_constants(self):
        assert exp.EXP_TYPE_NIL == 0
        assert exp.EXP_TYPE_BOOL == 1
        assert exp.EXP_TYPE_INT == 2
        assert exp.EXP_TYPE_STRING == 3
        assert exp.EXP_TYPE_LIST == 4
        assert exp.EXP_TYPE_MAP == 5
        assert exp.EXP_TYPE_BLOB == 6
        assert exp.EXP_TYPE_FLOAT == 7
        assert exp.EXP_TYPE_GEO == 8
        assert exp.EXP_TYPE_HLL == 9


class TestExpModuleAccess:
    def test_exp_module(self):
        assert hasattr(exp, "eq")
        assert hasattr(exp, "int_bin")
        assert hasattr(exp, "and_")
        assert hasattr(exp, "ttl")
        assert hasattr(exp, "regex_compare")


class TestExpComplexExpressions:
    def test_nested_and_or(self):
        """Test complex nested expression: (age >= 18 AND age < 65) OR role == 'admin'."""
        e = exp.or_(
            exp.and_(
                exp.ge(exp.int_bin("age"), exp.int_val(18)),
                exp.lt(exp.int_bin("age"), exp.int_val(65)),
            ),
            exp.eq(exp.string_bin("role"), exp.string_val("admin")),
        )
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 2
        assert e["exprs"][0]["__expr__"] == "and"
        assert len(e["exprs"][0]["exprs"]) == 2

    def test_expression_in_policy_dict(self):
        """Test that expressions can be embedded in policy dicts."""
        expr = exp.ge(exp.int_bin("age"), exp.int_val(21))
        policy = {"filter_expression": expr, "socket_timeout": 5000}
        assert policy["filter_expression"]["__expr__"] == "ge"
        assert policy["socket_timeout"] == 5000
