"""Verify that aerospike_py constant values match the official aerospike client.

Some constants have different names or values between aerospike-py and the
official client.  This test covers constants whose names AND values are
identical in both libraries.  Constants that are intentionally mapped
differently (e.g. aerospike-py POLICY_EXISTS_CREATE_ONLY vs official
POLICY_EXISTS_CREATE) are tested separately as name-mapping pairs.
"""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

# Constants whose names are identical in both libraries
IDENTICAL_CONSTANTS = [
    # Policy Key
    "POLICY_KEY_DIGEST",
    "POLICY_KEY_SEND",
    # Policy Exists
    "POLICY_EXISTS_IGNORE",
    # Policy Gen
    "POLICY_GEN_IGNORE",
    "POLICY_GEN_EQ",
    "POLICY_GEN_GT",
    # Policy Replica
    "POLICY_REPLICA_MASTER",
    # Policy Commit Level
    "POLICY_COMMIT_LEVEL_ALL",
    "POLICY_COMMIT_LEVEL_MASTER",
    # TTL Constants
    "TTL_NAMESPACE_DEFAULT",
    # Operator Constants
    "OPERATOR_APPEND",
    "OPERATOR_PREPEND",
    "OPERATOR_TOUCH",
    # Index Collection Type
    "INDEX_TYPE_DEFAULT",
    "INDEX_TYPE_LIST",
    "INDEX_TYPE_MAPKEYS",
    "INDEX_TYPE_MAPVALUES",
    # Log Level
    "LOG_LEVEL_ERROR",
    "LOG_LEVEL_WARN",
    "LOG_LEVEL_INFO",
    "LOG_LEVEL_DEBUG",
    "LOG_LEVEL_TRACE",
]


@pytest.mark.parametrize("name", IDENTICAL_CONSTANTS)
def test_constant_value_matches(name):
    rust_val = getattr(aerospike_py, name)
    off_val = getattr(aerospike, name)
    assert rust_val == off_val, f"{name}: aerospike_py={rust_val} != aerospike={off_val}"


# Constants whose names differ between the two libraries
# (aerospike_py_name, official_name)
MAPPED_CONSTANTS = [
    ("POLICY_EXISTS_CREATE_ONLY", "POLICY_EXISTS_CREATE"),
    ("POLICY_EXISTS_REPLACE", "POLICY_EXISTS_REPLACE"),
    ("POLICY_EXISTS_UPDATE", "POLICY_EXISTS_UPDATE"),
]


@pytest.mark.parametrize("rust_name,off_name", MAPPED_CONSTANTS)
def test_mapped_constant_exists(rust_name, off_name):
    """Both libraries expose the constant (possibly under different names)."""
    assert hasattr(aerospike_py, rust_name), f"aerospike_py missing {rust_name}"
    assert hasattr(aerospike, off_name), f"aerospike missing {off_name}"
