"""Unit tests for import and basic module structure (no server required)."""

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


def test_client_not_connected_raises():
    """Test that calling methods on unconnected client raises ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    try:
        c.get(("test", "demo", "key1"))
        assert False, "Should have raised ClientError"
    except aerospike_py.ClientError:
        pass


def test_constants():
    """Test that all key constants are defined."""
    # Policy Key
    assert aerospike_py.POLICY_KEY_DIGEST == 0
    assert aerospike_py.POLICY_KEY_SEND == 1

    # Policy Exists
    assert aerospike_py.POLICY_EXISTS_IGNORE == 0
    assert aerospike_py.POLICY_EXISTS_UPDATE == 1
    assert aerospike_py.POLICY_EXISTS_UPDATE_ONLY == 1
    assert aerospike_py.POLICY_EXISTS_REPLACE == 2
    assert aerospike_py.POLICY_EXISTS_REPLACE_ONLY == 3
    assert aerospike_py.POLICY_EXISTS_CREATE_ONLY == 4

    # Policy Gen
    assert aerospike_py.POLICY_GEN_IGNORE == 0
    assert aerospike_py.POLICY_GEN_EQ == 1
    assert aerospike_py.POLICY_GEN_GT == 2

    # TTL
    assert aerospike_py.TTL_NAMESPACE_DEFAULT == 0
    assert aerospike_py.TTL_NEVER_EXPIRE == -1
    assert aerospike_py.TTL_DONT_UPDATE == -2

    # Operators
    assert aerospike_py.OPERATOR_READ == 1
    assert aerospike_py.OPERATOR_WRITE == 2
    assert aerospike_py.OPERATOR_INCR == 5
    assert aerospike_py.OPERATOR_APPEND == 9
    assert aerospike_py.OPERATOR_PREPEND == 10
    assert aerospike_py.OPERATOR_TOUCH == 11
    assert aerospike_py.OPERATOR_DELETE == 12

    # Status codes
    assert aerospike_py.AEROSPIKE_OK == 0
    assert aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND == 2
    assert aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS == 5
    assert aerospike_py.AEROSPIKE_ERR_TIMEOUT == 9


def test_exception_hierarchy():
    """Test that exception classes follow proper hierarchy."""
    assert issubclass(aerospike_py.ClientError, aerospike_py.AerospikeError)
    assert issubclass(aerospike_py.ServerError, aerospike_py.AerospikeError)
    assert issubclass(aerospike_py.RecordError, aerospike_py.AerospikeError)
    assert issubclass(aerospike_py.ClusterError, aerospike_py.AerospikeError)
    assert issubclass(aerospike_py.AerospikeTimeoutError, aerospike_py.AerospikeError)
    assert issubclass(aerospike_py.TimeoutError, aerospike_py.AerospikeError)
    assert aerospike_py.AerospikeTimeoutError is aerospike_py.TimeoutError
    assert issubclass(aerospike_py.InvalidArgError, aerospike_py.AerospikeError)

    # Record-level subclasses
    assert issubclass(aerospike_py.RecordNotFound, aerospike_py.RecordError)
    assert issubclass(aerospike_py.RecordExistsError, aerospike_py.RecordError)
    assert issubclass(aerospike_py.RecordGenerationError, aerospike_py.RecordError)
    assert issubclass(aerospike_py.RecordTooBig, aerospike_py.RecordError)
    assert issubclass(aerospike_py.BinNameError, aerospike_py.RecordError)
    assert issubclass(aerospike_py.BinExistsError, aerospike_py.RecordError)
    assert issubclass(aerospike_py.BinNotFound, aerospike_py.RecordError)
    assert issubclass(aerospike_py.BinTypeError, aerospike_py.RecordError)
    assert issubclass(aerospike_py.FilteredOut, aerospike_py.RecordError)

    # Same classes accessible from exception module
    assert issubclass(exception.RecordNotFound, aerospike_py.RecordError)
    assert issubclass(exception.RecordExistsError, aerospike_py.RecordError)
    assert issubclass(exception.BinNameError, aerospike_py.RecordError)
    assert issubclass(exception.AerospikeIndexError, aerospike_py.ServerError)
    assert exception.AerospikeIndexError is exception.IndexError
    assert issubclass(exception.IndexNotFound, exception.AerospikeIndexError)
    assert issubclass(exception.IndexNotFound, exception.IndexError)
    assert issubclass(exception.QueryAbortedError, exception.QueryError)
    assert issubclass(exception.AdminError, aerospike_py.ServerError)
    assert issubclass(exception.UDFError, aerospike_py.ServerError)

    # Verify exception module classes are the same objects as aerospike module classes
    assert exception.RecordNotFound is aerospike_py.RecordNotFound
    assert exception.IndexNotFound is aerospike_py.IndexNotFound


def test_client_not_connected_operations():
    """Test that various methods on unconnected client raise ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    key = ("test", "demo", "key1")

    for method, args in [
        ("put", (key, {"a": 1})),
        ("exists", (key,)),
        ("remove", (key,)),
        ("select", (key, ["a"])),
        ("touch", (key,)),
        ("append", (key, "a", "val")),
        ("prepend", (key, "a", "val")),
        ("increment", (key, "a", 1)),
    ]:
        try:
            getattr(c, method)(*args)
            assert False, f"{method}() should have raised ClientError"
        except aerospike_py.ClientError:
            pass


def test_sync_async_method_parity():
    """Verify Client and AsyncClient expose the same public API methods."""
    from aerospike_py._aerospike import AsyncClient as _NativeAsyncClient

    sync_methods = {
        m
        for m in dir(aerospike_py.Client)
        if not m.startswith("_") and callable(getattr(aerospike_py.Client, m))
    }
    async_methods = {
        m
        for m in dir(_NativeAsyncClient)
        if not m.startswith("_") and callable(getattr(_NativeAsyncClient, m))
    }

    # query() is sync-only (returns PyQuery object)
    sync_only_expected = {"query"}

    sync_extra = sync_methods - async_methods - sync_only_expected
    async_extra = async_methods - sync_methods

    assert not sync_extra, (
        f"Methods in Client but missing from AsyncClient: {sync_extra}"
    )
    assert not async_extra, (
        f"Methods in AsyncClient but missing from Client: {async_extra}"
    )


def test_exp_invalid_op_rejected():
    """Test that constructing an expression with invalid op raises ValueError."""
    from aerospike_py import exp

    try:
        exp._cmd("nonexistent_op", val=42)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent_op" in str(e)

    # Valid ops should work fine
    result = exp.int_val(42)
    assert result["__expr__"] == "int_val"
    assert result["val"] == 42


def test_connect_username_without_password():
    """Test that connect() with username but no password raises ClientError."""
    c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
    try:
        c.connect(username="admin")
        assert False, "Should have raised ClientError"
    except aerospike_py.ClientError:
        pass
