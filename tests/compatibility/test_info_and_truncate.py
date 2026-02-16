"""Info command and truncate operation compatibility tests.

Compares info_all, info_random_node return formats and truncate
behavior between aerospike-py and the official client.

Note: The two clients have different info_all return formats:
- aerospike-py: list[tuple[str, int, str]] - [(node_name, err_code, response), ...]
- official: dict[str, tuple[err|None, str]] - {node_name: (err, response), ...}
"""

import time

import pytest

aerospike = pytest.importorskip("aerospike")

NS = "test"
SET = "compat_info"


# ── info_all ───────────────────────────────────────────────────────


class TestInfoAll:
    """Compare info_all return format across clients."""

    def test_rust_info_all_return_type(self, rust_client):
        """Rust returns list of (node_name, error_code, response)."""
        result = rust_client.info_all("build")
        assert isinstance(result, list)
        assert len(result) >= 1

        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 3
            node_name, err_code, response = item
            assert isinstance(node_name, str)
            assert isinstance(err_code, int)
            assert isinstance(response, str)

    def test_official_info_all_return_type(self, official_client):
        """Official returns dict of {node_name: (err, response)}."""
        result = official_client.info_all("build")
        assert isinstance(result, dict)
        assert len(result) >= 1

        for node_name, val in result.items():
            assert isinstance(node_name, str)
            assert isinstance(val, tuple)
            assert len(val) == 2

    def test_info_all_build_version_matches(self, rust_client, official_client):
        """Both clients should see the same server build version."""
        r_result = rust_client.info_all("build")
        o_result = official_client.info_all("build")

        # Extract versions
        r_versions = sorted([resp.strip() for _, _, resp in r_result])
        o_versions = sorted([resp.strip() for _, val in o_result.items() for resp in [val[1]]])

        assert r_versions == o_versions

    def test_info_all_namespaces(self, rust_client, official_client):
        """Both should see the same namespaces."""
        r_result = rust_client.info_all("namespaces")
        o_result = official_client.info_all("namespaces")

        # Rust: list of tuples
        r_ns = r_result[0][2].strip()
        # Official: dict of (err, response)
        o_first_val = next(iter(o_result.values()))
        o_ns = o_first_val[1].strip()
        assert r_ns == o_ns

    def test_info_all_node_count_matches(self, rust_client, official_client):
        """Both clients should see the same number of nodes."""
        r_result = rust_client.info_all("build")
        o_result = official_client.info_all("build")

        assert len(r_result) == len(o_result)


# ── info_random_node ───────────────────────────────────────────────


class TestInfoRandomNode:
    """Compare info_random_node return format.

    Note: official client returns "command\\tresponse" format,
    while aerospike-py returns just the response string.
    """

    def test_info_random_node_return_type(self, rust_client, official_client):
        """Both should return a string response."""
        r_result = rust_client.info_random_node("build")
        o_result = official_client.info_random_node("build")

        assert isinstance(r_result, str)
        assert isinstance(o_result, str)

    def test_info_random_node_build_content(self, rust_client, official_client):
        """Both should contain the same build version, despite format differences."""
        r_build = rust_client.info_random_node("build").strip()
        o_raw = official_client.info_random_node("build").strip()

        # Official format: "build\t8.1.0.3" - extract version after tab
        o_build = o_raw.split("\t")[-1] if "\t" in o_raw else o_raw

        assert r_build == o_build, (
            f"Build version mismatch: rust='{r_build}', official='{o_build}' "
            f"(raw='{o_raw}'). Note: official prefixes command name."
        )

    def test_info_random_node_status(self, rust_client, official_client):
        """Server status should be available from both."""
        r_status = rust_client.info_random_node("status")
        o_status = official_client.info_random_node("status")

        assert isinstance(r_status, str)
        assert isinstance(o_status, str)


# ── Truncate ───────────────────────────────────────────────────────


_SKIP_TRUNCATE = "Aerospike truncate phantom read — server-side async propagation is non-deterministic"


class TestTruncateBehavior:
    """Verify truncate removes records and both clients see the result."""

    @pytest.mark.skip(reason=_SKIP_TRUNCATE)
    def test_rust_truncate_official_verify(self, rust_client, official_client):
        """Rust truncates, official verifies records are gone."""
        trunc_set = "compat_trunc_r"

        # Seed data
        keys = []
        for i in range(5):
            key = (NS, trunc_set, f"trunc_r_{i}")
            rust_client.put(key, {"val": i})
            keys.append(key)

        # Verify data exists
        for key in keys:
            _, meta, _ = official_client.get(key)
            assert meta is not None

        # Truncate
        rust_client.truncate(NS, trunc_set, 0)

        # Truncate is async on the server; poll until records are gone
        for _ in range(20):
            time.sleep(1)
            _, meta = official_client.exists(keys[-1])
            if meta is None:
                break

        # Verify all records are gone via official client
        for key in keys:
            _, meta = official_client.exists(key)
            assert meta is None, f"Record {key} still exists after truncate"

    @pytest.mark.skip(reason=_SKIP_TRUNCATE)
    def test_official_truncate_rust_verify(self, rust_client, official_client):
        """Official truncates, rust verifies records are gone."""
        trunc_set = "compat_trunc_o"

        # Seed data
        keys = []
        for i in range(5):
            key = (NS, trunc_set, f"trunc_o_{i}")
            official_client.put(key, {"val": i})
            keys.append(key)

        # Truncate via official client
        official_client.truncate(NS, trunc_set, 0)

        # Truncate is async on the server; poll until records are gone
        for _ in range(20):
            time.sleep(1)
            _, meta = rust_client.exists(keys[-1])
            if meta is None:
                break

        # Verify via rust client
        for key in keys:
            _, meta = rust_client.exists(key)
            assert meta is None, f"Record {key} still exists after truncate"

    @pytest.mark.skip(reason=_SKIP_TRUNCATE)
    def test_truncate_then_rewrite(self, rust_client, official_client):
        """After truncate, new writes should work normally."""
        trunc_set = "compat_trunc_rw"

        key = (NS, trunc_set, "rw_test")
        rust_client.put(key, {"val": "before"})

        rust_client.truncate(NS, trunc_set, 0)

        # Truncate is async on the server; poll until record is gone
        for _ in range(20):
            time.sleep(1)
            _, meta = rust_client.exists(key)
            if meta is None:
                break

        # Write new data
        rust_client.put(key, {"val": "after"})
        _, _, o_bins = official_client.get(key)
        assert o_bins["val"] == "after"

        # Cleanup
        try:
            rust_client.remove(key)
        except Exception:
            pass
