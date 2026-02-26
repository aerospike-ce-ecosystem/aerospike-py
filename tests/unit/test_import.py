"""Unit tests for import and basic module structure (no server required)."""

import pytest

import aerospike_py
from aerospike_py import exception


def test_import():
    """Test that aerospike_py module can be imported."""
    assert hasattr(aerospike_py, "__version__")
    # Version is now dynamic via importlib.metadata
    assert isinstance(aerospike_py.__version__, str)
    assert len(aerospike_py.__version__) > 0


def test_client_factory():
    """Test that aerospike_py.client() creates a Client."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    assert isinstance(c, aerospike_py.Client)
    assert not c.is_connected()


def test_async_client_factory():
    """Test that aerospike_py.async_client() creates an AsyncClient."""
    c = aerospike_py.async_client({"hosts": [("127.0.0.1", 3000)]})
    assert isinstance(c, aerospike_py.AsyncClient)
    assert not c.is_connected()


def test_client_not_connected_raises():
    """Test that calling methods on unconnected client raises ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    with pytest.raises(aerospike_py.ClientError):
        c.get(("test", "demo", "key1"))


# ── Constants tests (parametrized) ──────────────────────────────────


@pytest.mark.parametrize(
    "const_name,expected_value",
    [
        # Policy Key
        ("POLICY_KEY_DIGEST", 0),
        ("POLICY_KEY_SEND", 1),
        # Policy Exists
        ("POLICY_EXISTS_IGNORE", 0),
        ("POLICY_EXISTS_UPDATE", 1),
        ("POLICY_EXISTS_UPDATE_ONLY", 1),
        ("POLICY_EXISTS_REPLACE", 2),
        ("POLICY_EXISTS_REPLACE_ONLY", 3),
        ("POLICY_EXISTS_CREATE_ONLY", 4),
        # Policy Gen
        ("POLICY_GEN_IGNORE", 0),
        ("POLICY_GEN_EQ", 1),
        ("POLICY_GEN_GT", 2),
        # TTL
        ("TTL_NAMESPACE_DEFAULT", 0),
        ("TTL_NEVER_EXPIRE", -1),
        ("TTL_DONT_UPDATE", -2),
        # Operators
        ("OPERATOR_READ", 1),
        ("OPERATOR_WRITE", 2),
        ("OPERATOR_INCR", 5),
        ("OPERATOR_APPEND", 9),
        ("OPERATOR_PREPEND", 10),
        ("OPERATOR_TOUCH", 11),
        ("OPERATOR_DELETE", 12),
        # Status codes
        ("AEROSPIKE_OK", 0),
        ("AEROSPIKE_ERR_RECORD_NOT_FOUND", 2),
        ("AEROSPIKE_ERR_RECORD_EXISTS", 5),
        ("AEROSPIKE_ERR_TIMEOUT", 9),
    ],
)
def test_constants(const_name, expected_value):
    """Key constants are defined with expected values."""
    assert getattr(aerospike_py, const_name) == expected_value


# ── Exception hierarchy tests (parametrized) ────────────────────────


@pytest.mark.parametrize(
    "child,parent",
    [
        (aerospike_py.ClientError, aerospike_py.AerospikeError),
        (aerospike_py.ServerError, aerospike_py.AerospikeError),
        (aerospike_py.RecordError, aerospike_py.AerospikeError),
        (aerospike_py.ClusterError, aerospike_py.AerospikeError),
        (aerospike_py.AerospikeTimeoutError, aerospike_py.AerospikeError),
        (aerospike_py.TimeoutError, aerospike_py.AerospikeError),
        (aerospike_py.InvalidArgError, aerospike_py.AerospikeError),
        # Record-level subclasses
        (aerospike_py.RecordNotFound, aerospike_py.RecordError),
        (aerospike_py.RecordExistsError, aerospike_py.RecordError),
        (aerospike_py.RecordGenerationError, aerospike_py.RecordError),
        (aerospike_py.RecordTooBig, aerospike_py.RecordError),
        (aerospike_py.BinNameError, aerospike_py.RecordError),
        (aerospike_py.BinExistsError, aerospike_py.RecordError),
        (aerospike_py.BinNotFound, aerospike_py.RecordError),
        (aerospike_py.BinTypeError, aerospike_py.RecordError),
        (aerospike_py.FilteredOut, aerospike_py.RecordError),
        # Exception module classes
        (exception.RecordNotFound, aerospike_py.RecordError),
        (exception.RecordExistsError, aerospike_py.RecordError),
        (exception.BinNameError, aerospike_py.RecordError),
        (exception.AerospikeIndexError, aerospike_py.ServerError),
        (exception.IndexNotFound, exception.AerospikeIndexError),
        (exception.IndexNotFound, exception.IndexError),
        (exception.QueryAbortedError, exception.QueryError),
        (exception.AdminError, aerospike_py.ServerError),
        (exception.UDFError, aerospike_py.ServerError),
    ],
)
def test_exception_hierarchy(child, parent):
    """Exception classes follow proper inheritance hierarchy."""
    assert issubclass(child, parent)


def test_exception_aliases():
    """Deprecated aliases point to the same classes."""
    assert aerospike_py.AerospikeTimeoutError is aerospike_py.TimeoutError
    assert exception.AerospikeIndexError is exception.IndexError
    assert exception.RecordNotFound is aerospike_py.RecordNotFound
    assert exception.IndexNotFound is aerospike_py.IndexNotFound


# ── Unconnected client operations tests (parametrized) ──────────────


@pytest.mark.parametrize(
    "method,args",
    [
        ("put", (("test", "demo", "key1"), {"a": 1})),
        ("get", (("test", "demo", "key1"),)),
        ("exists", (("test", "demo", "key1"),)),
        ("remove", (("test", "demo", "key1"),)),
        ("select", (("test", "demo", "key1"), ["a"])),
        ("touch", (("test", "demo", "key1"),)),
        ("append", (("test", "demo", "key1"), "a", "val")),
        ("prepend", (("test", "demo", "key1"), "a", "val")),
        ("increment", (("test", "demo", "key1"), "a", 1)),
        ("operate", (("test", "demo", "key1"), [{"op": 1, "bin": "a", "val": 1}])),
        ("operate_ordered", (("test", "demo", "key1"), [{"op": 1, "bin": "a", "val": 1}])),
        ("remove_bin", (("test", "demo", "key1"), ["a"])),
        ("batch_read", ([("test", "demo", "key1")],)),
        ("batch_operate", ([("test", "demo", "key1")], [{"op": 1, "bin": "a", "val": 1}])),
        ("batch_remove", ([("test", "demo", "key1")],)),
        ("info_all", ("status",)),
    ],
)
def test_client_not_connected_operations(method, args):
    """Various methods on unconnected client raise ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    with pytest.raises(aerospike_py.ClientError):
        getattr(c, method)(*args)


def test_sync_async_method_parity():
    """Verify Client and AsyncClient expose the same public API methods."""
    from aerospike_py._aerospike import AsyncClient as _NativeAsyncClient

    sync_methods = {
        m for m in dir(aerospike_py.Client) if not m.startswith("_") and callable(getattr(aerospike_py.Client, m))
    }
    async_methods = {
        m for m in dir(_NativeAsyncClient) if not m.startswith("_") and callable(getattr(_NativeAsyncClient, m))
    }

    # query() is sync-only (returns PyQuery object)
    sync_only_expected = {"query"}

    sync_extra = sync_methods - async_methods - sync_only_expected
    async_extra = async_methods - sync_methods

    assert not sync_extra, f"Methods in Client but missing from AsyncClient: {sync_extra}"
    assert not async_extra, f"Methods in AsyncClient but missing from Client: {async_extra}"


def test_exp_invalid_op_rejected():
    """Test that constructing an expression with invalid op raises ValueError."""
    from aerospike_py import exp

    with pytest.raises(ValueError, match="nonexistent_op"):
        exp._cmd("nonexistent_op", val=42)

    # Valid ops should work fine
    result = exp.int_val(42)
    assert result["__expr__"] == "int_val"
    assert result["val"] == 42


def test_list_map_op_codes_contiguous():
    """Verify list/map operation code constants are contiguous and match expected ranges."""
    from aerospike_py import list_operations, map_operations

    # Collect all _OP_LIST_* constants
    list_ops = {name: getattr(list_operations, name) for name in dir(list_operations) if name.startswith("_OP_LIST_")}
    list_codes = sorted(list_ops.values())
    assert list_codes[0] == 1001, f"List ops should start at 1001, got {list_codes[0]}"
    assert list_codes == list(range(1001, 1001 + len(list_codes))), f"List op codes are not contiguous: {list_codes}"

    # Collect all _OP_MAP_* constants
    map_ops = {name: getattr(map_operations, name) for name in dir(map_operations) if name.startswith("_OP_MAP_")}
    map_codes = sorted(map_ops.values())
    assert map_codes[0] == 2001, f"Map ops should start at 2001, got {map_codes[0]}"
    assert map_codes == list(range(2001, 2001 + len(map_codes))), f"Map op codes are not contiguous: {map_codes}"


def test_connect_username_without_password():
    """Test that connect() with username but no password raises ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    with pytest.raises(aerospike_py.ClientError):
        c.connect(username="admin")
