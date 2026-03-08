---
sidebar_position: 10
title: Troubleshooting
description: Common problems and solutions when using aerospike-py.
---

# Troubleshooting

This guide covers common issues you may encounter when using aerospike-py, along with their causes and solutions.

## Connection Issues

### ClusterError: Failed to connect

**Symptoms:**

```python
aerospike_py.ClusterError: Failed to connect to host(s)
```

**Causes:**
- Aerospike server is not running
- Incorrect host or port in the client configuration
- Firewall blocking the connection
- Cluster name mismatch

**Solutions:**

1. Verify the Aerospike server is running:
   ```bash
   # If using Podman
   podman ps | grep aerospike

   # Check if the port is open
   nc -zv 127.0.0.1 3000
   ```

2. Double-check your configuration:
   ```python
   client = aerospike_py.client({
       "hosts": [("127.0.0.1", 3000)],     # verify host and port
       "cluster_name": "my-cluster",         # must match server config
   }).connect()
   ```

3. If running in a container, ensure the port is correctly mapped and accessible from the host network.

### TimeoutError

**Symptoms:**

```python
aerospike_py.AerospikeTimeoutError: Operation timed out
```

**Causes:**
- Network latency between client and server
- Server overloaded or unresponsive
- Default timeout too low for your workload

**Solutions:**

1. Increase the timeout in the relevant policy:
   ```python
   # Per-operation timeout
   record = client.get(key, policy={"timeout": 5000})  # 5 seconds

   # Client-wide default
   client = aerospike_py.client({
       "hosts": [("127.0.0.1", 3000)],
       "policies": {
           "read": {"timeout": 5000},
           "write": {"timeout": 5000},
       },
   }).connect()
   ```

2. Check server health:
   ```python
   info = client.info_all("status")
   print(info)  # should return "ok" from each node
   ```

### "Client not connected" Error

**Symptoms:**

```python
aerospike_py.ClientError: Client is not connected
```

**Causes:**
- `connect()` was never called
- The connection was dropped (e.g., server restart) and not re-established
- `close()` was called before the operation

**Solutions:**

1. Always call `connect()` before performing operations:
   ```python
   client = aerospike_py.client(config).connect()
   ```

2. Use a context manager to ensure proper lifecycle:
   ```python
   with aerospike_py.client(config).connect() as client:
       record = client.get(key)
   # client.close() is called automatically
   ```

3. For async code:
   ```python
   async with aerospike_py.AsyncClient(config) as client:
       await client.connect()
       record = await client.get(key)
   ```

## Build and Installation Issues

### Build Failure (maturin)

**Symptoms:**

```
error: can't find Rust compiler
# or
ERROR: Failed building wheel for aerospike-py
```

**Causes:**
- Rust toolchain not installed
- Incompatible Rust version
- Missing system dependencies

**Solutions:**

1. For most users, pre-built wheels are available -- just use pip:
   ```bash
   pip install aerospike-py
   ```

2. If building from source, install the Rust toolchain:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   rustup default stable
   ```

3. Ensure you have a compatible Python version (3.10+, CPython only):
   ```bash
   python --version  # must be 3.10 or later
   ```

4. For development builds:
   ```bash
   pip install maturin
   maturin develop --release
   ```

### ImportError: Native Module Not Found

**Symptoms:**

```python
ImportError: cannot import name '_aerospike' from 'aerospike_py'
# or
ModuleNotFoundError: No module named 'aerospike_py._aerospike'
```

**Causes:**
- The package was not installed correctly
- Building from source without running `maturin develop`
- Using PyPy instead of CPython (not supported)

**Solutions:**

1. Install from PyPI:
   ```bash
   pip install aerospike-py
   ```

2. If developing locally, rebuild the native module:
   ```bash
   maturin develop --release
   ```

3. Verify you are using CPython:
   ```bash
   python -c "import platform; print(platform.python_implementation())"
   # Must print: CPython
   ```

## Runtime Issues

### NumPy-Related Errors

**Symptoms:**

```python
ImportError: numpy is required for batch_read_numpy
# or
TypeError: numpy dtype mismatch
```

**Causes:**
- NumPy is not installed
- NumPy version is incompatible (requires >= 2.0)

**Solutions:**

1. Install the NumPy extra:
   ```bash
   pip install "aerospike-py[numpy]"
   ```

2. Verify the NumPy version:
   ```bash
   python -c "import numpy; print(numpy.__version__)"
   # Must be 2.0 or later
   ```

3. Ensure your dtype fields match the bin types stored in Aerospike:
   ```python
   import numpy as np

   dtype = np.dtype([
       ("_key", "U64"),    # string key
       ("score", "f8"),    # float bin
       ("count", "i4"),    # integer bin
   ])
   results = client.batch_read(keys, bins=["score", "count"], _dtype=dtype)
   ```

### OpenTelemetry Tracing Not Working

**Symptoms:**
- No traces appearing in your collector (Jaeger, Zipkin, etc.)
- `init_tracing()` runs without error but no spans are exported

**Causes:**
- OpenTelemetry SDK not installed
- OTLP exporter not configured
- Collector not running or unreachable

**Solutions:**

1. Install the OTel extra:
   ```bash
   pip install "aerospike-py[otel]"
   ```

2. Initialize tracing in your application:
   ```python
   from aerospike_py import init_tracing, shutdown_tracing

   init_tracing()
   ```

3. Configure the OTLP endpoint via environment variables:
   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
   export OTEL_SERVICE_NAME="my-service"
   ```

4. Ensure your collector (e.g., Jaeger, Grafana Tempo) is running and accepting OTLP gRPC on the configured port.

5. Always call `shutdown_tracing()` before your application exits to flush pending spans.

### Prometheus Metrics Not Appearing

**Symptoms:**
- `get_metrics()` returns empty or no histogram data
- Metrics server returns no data

**Solutions:**

1. Verify metrics are enabled:
   ```python
   from aerospike_py import is_metrics_enabled, set_metrics_enabled

   print(is_metrics_enabled())  # should be True
   set_metrics_enabled(True)    # enable if disabled
   ```

2. Perform some operations first -- metrics are only recorded after operations execute.

3. If using the built-in metrics server:
   ```python
   from aerospike_py import start_metrics_server

   start_metrics_server(9090)
   # Then visit http://localhost:9090/metrics
   ```

## Python 3.14t (Free-Threaded) Notes

aerospike-py supports Python 3.14t (free-threaded / no-GIL builds). However, keep in mind:

- **Experimental support**: Free-threaded Python is still experimental in CPython. Some third-party libraries may not work correctly.
- **Thread safety**: aerospike-py's `Client` and `AsyncClient` are thread-safe. The Rust client handles internal synchronization.
- **Performance characteristics**: Without the GIL, true parallelism is possible across Python threads. However, the Tokio runtime worker count (`AEROSPIKE_RUNTIME_WORKERS`) may need tuning since GIL contention is no longer a factor.

If you encounter issues specific to free-threaded Python, try:

1. Falling back to a standard CPython build to isolate the issue.
2. Checking the [GitHub issues](https://github.com/KimSoungRyoul/aerospike-py/issues) for known free-threaded compatibility problems.

## Getting Help

If your issue is not covered here:

1. Check the [GitHub Issues](https://github.com/KimSoungRyoul/aerospike-py/issues) for existing reports.
2. Open a new issue with:
   - Python version (`python --version`)
   - aerospike-py version (`python -c "import aerospike_py; print(aerospike_py.__version__)"`)
   - Operating system and architecture
   - Complete error traceback
   - Minimal reproduction code
