"""Cross-client data type compatibility: write with one client, read with the other."""

import pytest


def _put_and_cross_read(writer, reader, key, bin_name, value):
    """Helper: writer puts value, reader reads it back."""
    writer.put(key, {bin_name: value})
    _, _, bins = reader.get(key)
    return bins[bin_name]


class TestInteger:
    @pytest.mark.parametrize("val", [42, -999, 0, 2**62])
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"int_r2o_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    @pytest.mark.parametrize("val", [42, -999, 0, 2**62])
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"int_o2r_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestString:
    @pytest.mark.parametrize(
        "val",
        ["hello", "", "x" * 100_000],
        ids=["simple", "empty", "large"],
    )
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"str_r2o_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    def test_unicode_rust_write_official_read(
        self, rust_client, official_client, cleanup
    ):
        key = ("test", "compat", "str_unicode_r2o")
        cleanup.append(key)
        val = "한글🎉"
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    def test_unicode_official_write_rust_read(
        self, rust_client, official_client, cleanup
    ):
        key = ("test", "compat", "str_unicode_o2r")
        cleanup.append(key)
        val = "한글🎉"
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestFloat:
    @pytest.mark.parametrize("val", [3.14, 0.0, -1.5])
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"float_r2o_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert abs(result - val) < 1e-9

    @pytest.mark.parametrize("val", [3.14, 0.0, -1.5])
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"float_o2r_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert abs(result - val) < 1e-9


class TestBytes:
    @pytest.mark.parametrize(
        "val",
        [b"\x00\x01\x02", b"", bytes(range(256)) * 10],
        ids=["simple", "empty", "large"],
    )
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"bytes_r2o_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    @pytest.mark.parametrize(
        "val",
        [b"\x00\x01\x02", b"", bytes(range(256)) * 10],
        ids=["simple", "empty", "large"],
    )
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"bytes_o2r_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestList:
    @pytest.mark.parametrize(
        "val",
        [[1, "two", 3.0], [], [[1, 2], [3, 4]]],
        ids=["mixed", "empty", "nested"],
    )
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"list_r2o_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    @pytest.mark.parametrize(
        "val",
        [[1, "two", 3.0], [], [[1, 2], [3, 4]]],
        ids=["mixed", "empty", "nested"],
    )
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"list_o2r_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestMap:
    @pytest.mark.parametrize(
        "val",
        [{"k": "v"}, {}, {"a": {"b": {"c": 1}}}],
        ids=["simple", "empty", "nested"],
    )
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"map_r2o_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    @pytest.mark.parametrize(
        "val",
        [{"k": "v"}, {}, {"a": {"b": {"c": 1}}}],
        ids=["simple", "empty", "nested"],
    )
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"map_o2r_{len(val)}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestBool:
    @pytest.mark.parametrize("val", [True, False])
    def test_rust_write_official_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"bool_r2o_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(rust_client, official_client, key, "v", val)
        assert result == val

    @pytest.mark.parametrize("val", [True, False])
    def test_official_write_rust_read(self, rust_client, official_client, cleanup, val):
        key = ("test", "compat", f"bool_o2r_{val}")
        cleanup.append(key)
        result = _put_and_cross_read(official_client, rust_client, key, "v", val)
        assert result == val


class TestNoneBin:
    """Aerospike treats None bin value as bin deletion."""

    def test_none_removes_bin_rust(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "none_rust")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": 2})
        rust_client.put(key, {"b": None})
        _, _, bins = official_client.get(key)

        assert "a" in bins
        assert "b" not in bins

    def test_none_removes_bin_official(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "none_off")
        cleanup.append(key)

        official_client.put(key, {"a": 1, "b": 2})
        official_client.put(key, {"b": None})
        _, _, bins = rust_client.get(key)

        assert "a" in bins
        assert "b" not in bins


class TestMixedComplex:
    """Deep nested structure cross-client test."""

    def test_complex_rust_write_official_read(
        self, rust_client, official_client, cleanup
    ):
        key = ("test", "compat", "complex_r2o")
        cleanup.append(key)

        data = {
            "users": [
                {"name": "Alice", "scores": [95, 87, 92]},
                {"name": "Bob", "scores": [78, 82, 90]},
            ],
            "metadata": {"version": 2, "tags": ["test", "compat"]},
        }
        rust_client.put(key, {"val": data})
        _, _, bins = official_client.get(key)

        assert bins["val"]["users"][0]["name"] == "Alice"
        assert bins["val"]["users"][1]["scores"] == [78, 82, 90]
        assert bins["val"]["metadata"]["tags"] == ["test", "compat"]

    def test_complex_official_write_rust_read(
        self, rust_client, official_client, cleanup
    ):
        key = ("test", "compat", "complex_o2r")
        cleanup.append(key)

        data = {
            "users": [
                {"name": "Alice", "scores": [95, 87, 92]},
                {"name": "Bob", "scores": [78, 82, 90]},
            ],
            "metadata": {"version": 2, "tags": ["test", "compat"]},
        }
        official_client.put(key, {"val": data})
        _, _, bins = rust_client.get(key)

        assert bins["val"]["users"][0]["name"] == "Alice"
        assert bins["val"]["users"][1]["scores"] == [78, 82, 90]
        assert bins["val"]["metadata"]["tags"] == ["test", "compat"]
