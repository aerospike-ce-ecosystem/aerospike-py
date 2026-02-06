"""Verify that aerospike_py constant values match the official aerospike client."""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

CONSTANT_NAMES = [
    # Policy Key
    "POLICY_KEY_DIGEST",
    "POLICY_KEY_SEND",
    # Policy Exists
    "POLICY_EXISTS_IGNORE",
    "POLICY_EXISTS_UPDATE",
    "POLICY_EXISTS_CREATE_ONLY",
    # Policy Gen
    "POLICY_GEN_IGNORE",
    "POLICY_GEN_EQ",
    "POLICY_GEN_GT",
    # Policy Replica
    "POLICY_REPLICA_MASTER",
    "POLICY_REPLICA_SEQUENCE",
    "POLICY_REPLICA_PREFER_RACK",
    # Policy Commit Level
    "POLICY_COMMIT_LEVEL_ALL",
    "POLICY_COMMIT_LEVEL_MASTER",
    # TTL Constants
    "TTL_NAMESPACE_DEFAULT",
    "TTL_NEVER_EXPIRE",
    "TTL_DONT_UPDATE",
    "TTL_CLIENT_DEFAULT",
    # Operator Constants
    "OPERATOR_READ",
    "OPERATOR_WRITE",
    "OPERATOR_INCR",
    "OPERATOR_APPEND",
    "OPERATOR_PREPEND",
    "OPERATOR_TOUCH",
    "OPERATOR_DELETE",
    # Index Type
    "INDEX_NUMERIC",
    "INDEX_STRING",
    "INDEX_GEO2DSPHERE",
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


@pytest.mark.parametrize("name", CONSTANT_NAMES)
def test_constant_value_matches(name):
    rust_val = getattr(aerospike_py, name)
    off_val = getattr(aerospike, name)
    assert (
        rust_val == off_val
    ), f"{name}: aerospike_py={rust_val} != aerospike={off_val}"
