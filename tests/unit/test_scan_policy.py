"""Unit tests for ``ScanPolicy`` TypedDict (#316).

These tests cover the Python user-facing surface only — the Rust layer
currently reuses the ``QueryPolicy`` parser for scan calls. When
``aerospike-core`` exposes a dedicated ``ScanPolicy`` struct, additional
parser-level tests will be added.
"""

from typing import get_type_hints

import aerospike_py
from aerospike_py.types import ScanPolicy


def test_scan_policy_importable_from_top_level():
    """``ScanPolicy`` is exported from the top-level ``aerospike_py`` package."""
    assert aerospike_py.ScanPolicy is ScanPolicy
    assert "ScanPolicy" in aerospike_py.__all__


def test_scan_policy_empty_dict_is_valid():
    """All fields are optional — empty ``ScanPolicy()`` must be allowed."""
    policy: ScanPolicy = ScanPolicy()
    assert policy == {}


def test_scan_policy_with_scan_specific_fields():
    """``records_per_second`` and ``max_records`` are scan-specific fields."""
    policy: ScanPolicy = ScanPolicy(records_per_second=1000, max_records=10000)
    assert policy["records_per_second"] == 1000
    assert policy["max_records"] == 10000


def test_scan_policy_full_field_set():
    """All fields documented in issue #316 round-trip through the TypedDict."""
    policy: ScanPolicy = ScanPolicy(
        socket_timeout=30000,
        total_timeout=0,
        max_retries=2,
        timeout_delay=0,
        filter_expression=None,
        replica=aerospike_py.POLICY_REPLICA_SEQUENCE,
        read_mode_ap=aerospike_py.POLICY_READ_MODE_AP_ONE,
        records_per_second=500,
        max_records=5000,
        durable_delete=False,
        ttl=0,
        partition_filter=None,
    )
    expected_fields = {
        "socket_timeout",
        "total_timeout",
        "max_retries",
        "timeout_delay",
        "filter_expression",
        "replica",
        "read_mode_ap",
        "records_per_second",
        "max_records",
        "durable_delete",
        "ttl",
        "partition_filter",
    }
    assert set(policy.keys()) == expected_fields


def test_scan_policy_field_annotations():
    """Annotated keys match the documented fields (catches accidental drift)."""
    hints = get_type_hints(ScanPolicy)
    expected_fields = {
        "socket_timeout",
        "total_timeout",
        "max_retries",
        "timeout_delay",
        "filter_expression",
        "replica",
        "read_mode_ap",
        "records_per_second",
        "max_records",
        "durable_delete",
        "ttl",
        "partition_filter",
    }
    assert set(hints.keys()) == expected_fields


def test_scan_policy_total_false():
    """``ScanPolicy`` uses ``total=False`` so all keys are optional."""
    # __total__ is False on the TypedDict class itself
    assert ScanPolicy.__total__ is False
