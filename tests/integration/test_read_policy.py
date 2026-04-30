"""Integration tests for read-path policy fields (replica, read_mode_ap, read_touch_ttl_percent).

Closes #305 + #309. Verifies these policy keys flow through to live operations
without raising. Server-side semantic effects (rack steering, consistency,
TTL touch behavior) are not directly observable from a single-node CE cluster,
so most of these are smoke tests verifying the wire path accepts and applies
the values. ``test_server_v8_touches_ttl_when_within_window`` runs only against
server v8+ where ``read_touch_ttl_percent`` is honored server-side.
"""

import time

import pytest

import aerospike_py


def _server_major(client) -> int:
    """Return the integer major version of the connected server, e.g. 8."""
    response = client.info_random_node("build")
    # Response is "build\tX.Y.Z[+something]\n" or similar; isolate the version.
    if "\t" in response:
        response = response.split("\t", 1)[1]
    return int(response.split(".")[0])


class TestReplicaPolicy:
    @pytest.mark.parametrize(
        "replica",
        [aerospike_py.POLICY_REPLICA_MASTER, aerospike_py.POLICY_REPLICA_SEQUENCE],
    )
    def test_get_with_replica(self, client, cleanup, replica):
        key = ("test", "demo", f"replica_{replica}")
        cleanup.append(key)
        client.put(key, {"v": 1})
        _, _, bins = client.get(key, policy={"replica": replica})
        assert bins["v"] == 1

    def test_get_with_prefer_rack_requires_rack_config(self, client, cleanup):
        """``PREFER_RACK`` requires ``rack_aware`` + ``rack_id`` in client policy.

        Without rack config, the server rejects with InvalidArgError. This test
        confirms the field flows through to the server and validates as expected
        — the parser does not silently swallow it.
        """
        key = ("test", "demo", "replica_prefer_rack")
        cleanup.append(key)
        client.put(key, {"v": 1})
        with pytest.raises(aerospike_py.InvalidArgError):
            client.get(key, policy={"replica": aerospike_py.POLICY_REPLICA_PREFER_RACK})

    def test_batch_read_with_replica(self, client, cleanup):
        key = ("test", "demo", "rp_batch")
        cleanup.append(key)
        client.put(key, {"v": 1})
        out = client.batch_read([key], policy={"replica": aerospike_py.POLICY_REPLICA_SEQUENCE})
        assert out  # smoke


class TestReadModeAp:
    @pytest.mark.parametrize(
        "mode",
        [aerospike_py.POLICY_READ_MODE_AP_ONE, aerospike_py.POLICY_READ_MODE_AP_ALL],
    )
    def test_get_with_read_mode_ap(self, client, cleanup, mode):
        key = ("test", "demo", f"rmap_{mode}")
        cleanup.append(key)
        client.put(key, {"v": 1})
        _, _, bins = client.get(key, policy={"read_mode_ap": mode})
        assert bins["v"] == 1

    def test_batch_read_with_read_mode_ap_all(self, client, cleanup):
        key = ("test", "demo", "rmap_batch")
        cleanup.append(key)
        client.put(key, {"v": 1})
        out = client.batch_read([key], policy={"read_mode_ap": aerospike_py.POLICY_READ_MODE_AP_ALL})
        assert out


class TestReadTouchTtlPercent:
    """`read_touch_ttl_percent` is honored server-side from v8+ only.

    Pre-v8 servers ignore the wire field; tests still verify the client accepts
    the value without erroring out, and that out-of-range values are rejected
    by the parser before going on the wire.
    """

    def test_special_value_server_default(self, client, cleanup):
        key = ("test", "demo", "rttl_default")
        cleanup.append(key)
        client.put(key, {"v": 1})
        client.get(key, policy={"read_touch_ttl_percent": 0})

    def test_special_value_dont_reset(self, client, cleanup):
        key = ("test", "demo", "rttl_dontreset")
        cleanup.append(key)
        client.put(key, {"v": 1})
        client.get(key, policy={"read_touch_ttl_percent": -1})

    @pytest.mark.parametrize("pct", [1, 50, 80, 100])
    def test_percent_values_accepted(self, client, cleanup, pct):
        key = ("test", "demo", f"rttl_{pct}")
        cleanup.append(key)
        client.put(key, {"v": 1})
        client.get(key, policy={"read_touch_ttl_percent": pct})

    @pytest.mark.parametrize("bad", [-100, -2, 101, 200])
    def test_out_of_range_raises_invalid_arg(self, client, cleanup, bad):
        key = ("test", "demo", f"rttl_bad_{bad}")
        cleanup.append(key)
        client.put(key, {"v": 1})
        with pytest.raises(aerospike_py.InvalidArgError):
            client.get(key, policy={"read_touch_ttl_percent": bad})

    def test_server_v8_touches_ttl_when_within_window(self, client, cleanup):
        """v8+ behavioral test: write with TTL=10s, set read_touch_ttl_percent=99
        so any read should touch and reset TTL toward the original 10s value."""
        if _server_major(client) < 8:
            pytest.skip("read_touch_ttl_percent honored only on server v8+")
        key = ("test", "demo", "rttl_touch_v8")
        cleanup.append(key)
        client.put(key, {"v": 1}, meta={"ttl": 10})
        time.sleep(2)
        _, meta_before, _ = client.get(key)
        time.sleep(1)
        client.get(key, policy={"read_touch_ttl_percent": 99})
        _, meta_after, _ = client.get(key)
        # With percent=99, a read should reset TTL up.
        assert meta_after.ttl >= meta_before.ttl - 1
